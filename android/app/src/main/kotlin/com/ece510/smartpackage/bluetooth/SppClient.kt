package com.ece510.smartpackage.bluetooth

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import androidx.annotation.RequiresPermission
import com.ece510.smartpackage.data.TripParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader
import java.util.UUID

/**
 * RFCOMM/SPP client for one Bluetooth session with the package's Pi
 * (src/offline/bt_server.py). The Pi only plays the SPP *server* role and
 * is reused unmodified — this class is the matching client half.
 *
 * Speaks the line protocol bt_server.py implements: once connected, the
 * Pi sends a banner line; after that, each command ("ALL\n") gets back
 * one JSON line per row, then a `{"done": N}` trailer.
 */
class SppClient(
    private val device: BluetoothDevice,
    private val adapter: BluetoothAdapter? = null,
) {

    private var socket: BluetoothSocket? = null
    private var reader: BufferedReader? = null

    /**
     * Opens the RFCOMM connection. Tries the standard, documented API
     * first; only falls back to the reflection-based channel API (some
     * Android Bluetooth stacks accept the SDP-backed socket object but
     * fail *during* `.connect()` with a native "read failed, socket might
     * closed or timeout" error) if that fails — see design doc point 6.
     *
     * The fallback must retry the actual `.connect()` call, not just
     * socket creation: `createRfcommSocketToServiceRecord()` always
     * succeeds (it just builds a Java object), so the failure this is
     * guarding against only ever shows up once `.connect()` is called.
     */
    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    suspend fun connect() = withContext(Dispatchers.IO) {
        // An in-progress discovery scan is a common real-world cause of the
        // native "read failed, socket might closed or timeout" error during
        // connect() — e.g. right after pairing from Android's Bluetooth
        // settings screen. Cancelling it here is a harmless no-op otherwise.
        runCatching { adapter?.cancelDiscovery() }

        val sock = connectViaServiceRecord() ?: connectViaFallbackChannel()
        socket = sock
        reader = BufferedReader(InputStreamReader(sock.inputStream, Charsets.UTF_8))
    }

    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private fun connectViaServiceRecord(): BluetoothSocket? {
        val sock = device.createRfcommSocketToServiceRecord(SPP_UUID)
        return try {
            sock.connect()
            sock
        } catch (_: IOException) {
            runCatching { sock.close() }
            null
        }
    }

    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private fun connectViaFallbackChannel(): BluetoothSocket {
        val sock = try {
            createFallbackSocket()
        } catch (e: Exception) {
            throw IOException(
                "Could not open RFCOMM socket via service record or fallback channel $FALLBACK_CHANNEL",
                e,
            )
        }
        try {
            sock.connect()
        } catch (e: IOException) {
            runCatching { sock.close() }
            throw e
        }
        return sock
    }

    /**
     * Plan B (design doc point 6): some Android Bluetooth stacks fail to
     * resolve the SDP "Serial Port" record even when the Pi advertises it
     * correctly. `createRfcommSocket` is a real but unlisted method on
     * BluetoothDevice; calling it via reflection opens a socket directly
     * on RFCOMM_CHANNEL (must match bt_server.py's RFCOMM_CHANNEL = 1).
     */
    private fun createFallbackSocket(): BluetoothSocket {
        val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
        return method.invoke(device, FALLBACK_CHANNEL) as BluetoothSocket
    }

    /**
     * Sends one command and collects every line of the reply up to and
     * including the `{"done": N}` trailer (used by both ALL and SYNC).
     * Caller is expected to wrap this in a timeout (e.g. withTimeout) —
     * a dropped connection mid-stream would otherwise block forever on
     * the underlying socket read.
     */
    suspend fun sendCommand(command: String): List<String> = withContext(Dispatchers.IO) {
        val sock = socket ?: error("SppClient.connect() must succeed before sendCommand()")
        val bufferedReader = reader ?: error("SppClient.connect() must succeed before sendCommand()")

        sock.outputStream.apply {
            write("$command\n".toByteArray(Charsets.UTF_8))
            flush()
        }

        val lines = mutableListOf<String>()
        while (true) {
            val line = bufferedReader.readLine() ?: break // peer closed the connection
            lines.add(line)
            if (TripParser.isDoneLine(line)) break
        }
        lines
    }

    /**
     * Sends a command that replies with a single JSON line (no `{"done": N}`
     * trailer), e.g. `RESET` (src/offline/bt_server.py). Skips any leading
     * non-JSON line — the connection banner if this is the first command
     * sent after connect() — and returns the first line starting with `{`,
     * or null if the peer closes the connection first.
     */
    suspend fun sendSimpleCommand(command: String): String? = withContext(Dispatchers.IO) {
        val sock = socket ?: error("SppClient.connect() must succeed before sendSimpleCommand()")
        val bufferedReader = reader ?: error("SppClient.connect() must succeed before sendSimpleCommand()")

        sock.outputStream.apply {
            write("$command\n".toByteArray(Charsets.UTF_8))
            flush()
        }

        var result: String? = null
        while (result == null) {
            val line = bufferedReader.readLine()?.trim() ?: return@withContext null
            if (line.startsWith("{")) result = line
        }
        result
    }

    /**
     * Like [sendCommand], but also stops when the peer sends a single
     * `{"error": ...}` line (used by `PHOTO <name>`, whose error replies
     * have no `{"done"}` trailer — see src/offline/bt_server.py
     * `_send_photo`). `sendCommand` itself stays unmodified so ALL/SYNC/
     * PHOTOS (which always end in `{"done"}`) keep working as before.
     */
    suspend fun sendCommandOrError(command: String): List<String> = withContext(Dispatchers.IO) {
        val sock = socket ?: error("SppClient.connect() must succeed before sendCommandOrError()")
        val bufferedReader = reader ?: error("SppClient.connect() must succeed before sendCommandOrError()")

        sock.outputStream.apply {
            write("$command\n".toByteArray(Charsets.UTF_8))
            flush()
        }

        val lines = mutableListOf<String>()
        while (true) {
            val line = bufferedReader.readLine() ?: break // peer closed the connection
            lines.add(line)
            if (TripParser.isDoneLine(line)) break
            val trimmed = line.trim()
            if (trimmed.startsWith("{") && trimmed.contains("\"error\"")) break
        }
        lines
    }

    /** Closes the socket; safe to call multiple times or after a failed connect(). */
    fun close() {
        runCatching { reader?.close() }
        runCatching { socket?.close() }
        reader = null
        socket = null
    }

    companion object {
        /** Standard Serial Port Profile UUID — matches what the Pi's SDP record advertises. */
        private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")

        /** Must match RFCOMM_CHANNEL in src/offline/bt_server.py. */
        private const val FALLBACK_CHANNEL = 1
    }
}
