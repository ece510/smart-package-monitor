package com.ece510.smartpackage.ui

import android.app.Application
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.ece510.smartpackage.bluetooth.SppClient
import com.ece510.smartpackage.data.TripParser
import com.ece510.smartpackage.domain.TripSummaryCalculator
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import java.io.IOException

private const val CONNECT_TIMEOUT_MS = 15_000L
private const val DOWNLOAD_TIMEOUT_MS = 20_000L

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

    private var lastDevice: BluetoothDevice? = null

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
    }

    private fun runTrip(device: BluetoothDevice) {
        viewModelScope.launch {
            _uiState.value = AppUiState.Connecting

            if (adapter?.isEnabled != true) {
                _uiState.value = AppUiState.Error("Bluetooth está apagado. Actívalo e inténtalo de nuevo.")
                return@launch
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
    }

    private fun describeFailure(e: Exception): String = when (e) {
        is TimeoutCancellationException ->
            "Tiempo de espera agotado. Comprueba que el paquete está cerca y encendido."
        is SecurityException ->
            "Falta el permiso de Bluetooth. Concédelo en Ajustes y vuelve a intentarlo."
        is IOException ->
            "No se pudo conectar: ${e.message ?: "conexión rechazada por el paquete"}."
        else ->
            e.message ?: "Error desconocido."
    }
}
