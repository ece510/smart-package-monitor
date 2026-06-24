package com.ece510.smartpackage.ui

import android.app.Application
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.ece510.smartpackage.bluetooth.SppClient
import com.ece510.smartpackage.data.PhotoData
import com.ece510.smartpackage.data.PhotoParser
import com.ece510.smartpackage.data.TripParser
import com.ece510.smartpackage.domain.TripSummaryCalculator
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import java.io.IOException

private const val CONNECT_TIMEOUT_MS = 15_000L
private const val DOWNLOAD_TIMEOUT_MS = 20_000L
// Covers ALLPHOTOS: every available photo's base64 bytes in one session, so
// this wraps the whole batch rather than a single row of text. Tune after
// testing with real hardware.
private const val PHOTOS_BATCH_TIMEOUT_MS = 60_000L

/**
 * Orchestrates one Bluetooth session end to end: pick a paired device,
 * connect, send `ALL`, parse, summarize. Each "connect and download" (or
 * refresh) is a fresh connect -> fetch -> close cycle rather than holding
 * the socket open between requests, since a worn RFCOMM link is more
 * likely to drop than a fresh connection is to fail.
 */
class TripViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow<AppUiState>(AppUiState.Idle)
    val uiState: StateFlow<AppUiState> = _uiState.asStateFlow()

    private val _photoState = MutableStateFlow<PhotoUiState>(PhotoUiState.Hidden)
    val photoState: StateFlow<PhotoUiState> = _photoState.asStateFlow()

    private var lastDevice: BluetoothDevice? = null

    // Guard against overlapping Bluetooth sessions: the Pi only accepts one
    // RFCOMM client at a time (bt_server.py's listen(1)), so tapping a
    // second action before the first finishes opens a second socket that
    // gets reset by the Pi — observed as a burst of "Connection from /
    // Connection reset by peer" in the Pi console. Ignoring the new tap
    // while one is already in flight is simpler and more correct than
    // cancelling-and-replacing, since only one connection can succeed
    // anyway.
    private var tripJob: Job? = null
    private var photoJob: Job? = null

    private val adapter: BluetoothAdapter?
        get() = (getApplication<Application>().getSystemService(BluetoothManager::class.java))
            ?.adapter

    /**
     * Devices already paired via Android Settings (design doc point 4: no
     * in-app scanning for the MVP). Returns an empty list if Bluetooth is
     * off or the permission hasn't been granted yet — callers should check
     * [isBluetoothEnabled] separately to tell those cases apart in the UI.
     */
    fun pairedDevices(): List<BluetoothDevice> =
        try {
            adapter?.bondedDevices?.toList() ?: emptyList()
        } catch (_: SecurityException) {
            emptyList()
        }

    fun isBluetoothEnabled(): Boolean = adapter?.isEnabled == true

    fun connectAndDownload(device: BluetoothDevice) {
        lastDevice = device
        runTrip(device)
    }

    /** Re-runs the same ALL fetch against the last connected device. */
    fun refresh() {
        lastDevice?.let { runTrip(it) }
    }

    fun reset() {
        _uiState.value = AppUiState.Idle
        _photoState.value = PhotoUiState.Hidden
    }

    /**
     * Sends RESET (src/offline/bt_server.py) to wipe the Pi's history, then
     * runs a fresh ALL so the screen reflects the now-empty trip. Done as two
     * separate connect/close cycles rather than reusing one socket — simpler
     * and more robust than juggling reader state across two different
     * response shapes (a single line for RESET vs. the ALL/done stream).
     */
    fun clearHistory() {
        if (tripJob?.isActive == true) return
        val device = lastDevice ?: return
        tripJob = viewModelScope.launch {
            _uiState.value = AppUiState.Connecting

            if (adapter?.isEnabled != true) {
                _uiState.value = AppUiState.Error("Bluetooth is off. Turn it on and try again.")
                return@launch
            }

            val client = SppClient(device, adapter)
            try {
                withTimeout(CONNECT_TIMEOUT_MS) { client.connect() }
                withTimeout(DOWNLOAD_TIMEOUT_MS) { client.sendSimpleCommand("RESET") }
            } catch (e: Exception) {
                _uiState.value = AppUiState.Error(describeFailure(e))
                return@launch
            } finally {
                client.close()
            }

            // Same tripJob is still active here, so call the unguarded body
            // directly rather than runTrip() (which would no-op on itself).
            doTrip(device)
        }
    }

    /** Opens the photo panel and downloads every available photo in one
     * ALLPHOTOS session, so browsing afterward needs no further Bluetooth
     * traffic (see selectPhoto()). */
    fun openPhotos() {
        if (photoJob?.isActive == true) return
        val device = lastDevice ?: return
        photoJob = viewModelScope.launch {
            _photoState.value = PhotoUiState.LoadingList

            if (adapter?.isEnabled != true) {
                _photoState.value = PhotoUiState.Error("Bluetooth is off. Turn it on and try again.")
                return@launch
            }

            val client = SppClient(device, adapter)
            // withTimeout can't interrupt a blocking BufferedReader.readLine()
            // inside sendCommand() — the underlying socket read just isn't
            // cooperative with coroutine cancellation. Without this watchdog,
            // a stalled transfer (e.g. the Pi taking far longer than expected
            // to send ALLPHOTOS) leaves the spinner stuck well past
            // PHOTOS_BATCH_TIMEOUT_MS instead of surfacing an error. Closing
            // the socket from outside makes the blocked readLine() throw
            // IOException, which unblocks sendCommand() and lets the
            // TimeoutCancellationException/catch below actually fire.
            val watchdog = launch {
                kotlinx.coroutines.delay(PHOTOS_BATCH_TIMEOUT_MS)
                client.close()
            }
            try {
                withTimeout(CONNECT_TIMEOUT_MS) { client.connect() }
                val lines = withTimeout(PHOTOS_BATCH_TIMEOUT_MS) { client.sendCommand("ALLPHOTOS") }
                val photos = PhotoParser.parseAll(lines)
                _photoState.value = PhotoUiState.ListLoaded(photos)
            } catch (e: Exception) {
                _photoState.value = PhotoUiState.Error(describePhotoFailure(e))
            } finally {
                watchdog.cancel()
                client.close()
            }
        }
    }

    /** Selects an already-downloaded photo to view. Purely local — all
     * photos were fetched up front by openPhotos(), so this needs no
     * Bluetooth session of its own. */
    fun selectPhoto(photo: PhotoData) {
        (_photoState.value as? PhotoUiState.ListLoaded)?.let {
            _photoState.value = it.copy(selected = photo)
        }
    }

    /** Closes the open photo but keeps the list. */
    fun closePhoto() {
        (_photoState.value as? PhotoUiState.ListLoaded)?.let {
            _photoState.value = it.copy(selected = null)
        }
    }

    /** Closes the whole photo panel, back to the trip view. */
    fun closePhotos() {
        _photoState.value = PhotoUiState.Hidden
    }

    private fun runTrip(device: BluetoothDevice) {
        if (tripJob?.isActive == true) return
        tripJob = viewModelScope.launch { doTrip(device) }
    }

    /** Connect -> ALL -> parse -> summarize, with no concurrency guard of its
     * own — callers (runTrip, clearHistory) are responsible for only
     * invoking this inside a job they've already claimed via tripJob. */
    private suspend fun doTrip(device: BluetoothDevice) {
        _uiState.value = AppUiState.Connecting

        if (adapter?.isEnabled != true) {
            _uiState.value = AppUiState.Error("Bluetooth is off. Turn it on and try again.")
            return
        }

        val client = SppClient(device, adapter)
        try {
            withTimeout(CONNECT_TIMEOUT_MS) { client.connect() }

            _uiState.value = AppUiState.Downloading
            val lines = withTimeout(DOWNLOAD_TIMEOUT_MS) { client.sendCommand("ALL") }

            val readings = TripParser.parseLines(lines)
            val summary = TripSummaryCalculator.summarize(readings)
            _uiState.value = AppUiState.Loaded(summary)
        } catch (e: Exception) {
            _uiState.value = AppUiState.Error(describeFailure(e))
        } finally {
            client.close()
        }
    }

    private fun describeFailure(e: Exception): String = when (e) {
        is TimeoutCancellationException ->
            "Timed out. Check that the package is nearby and powered on."
        is SecurityException ->
            "Bluetooth permission is missing. Grant it in Settings and try again."
        is IOException ->
            "Could not connect: ${e.message ?: "connection rejected by the package"}."
        else ->
            e.message ?: "Unknown error."
    }

    /** Extends describeFailure() for the photo flow with a transfer-size-aware
     * timeout message, rather than replacing the general-purpose one. */
    private fun describePhotoFailure(e: Exception): String = when (e) {
        is TimeoutCancellationException ->
            "The photo took too long to transfer. Move closer to the package and try again."
        else -> describeFailure(e)
    }
}
