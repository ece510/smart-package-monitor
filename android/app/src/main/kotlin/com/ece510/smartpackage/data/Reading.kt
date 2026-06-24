package com.ece510.smartpackage.data

/**
 * One row served by the Pi's BluetoothForwarder (src/offline/bt_server.py,
 * _row_to_json). Mirrors the SQLite schema in src/offline/store.py exactly:
 * sensor fields are nullable (a vision-only "CV" alert has no sensor values),
 * and [isAlert]/[alertReason] are decided by the Pi — this app never
 * recomputes them, it only displays what the Pi already decided.
 */
data class Reading(
    val id: Int,
    val ts: String, // ISO-8601 UTC, e.g. "2026-06-24T10:30:00.123456+00:00"
    val accelXg: Double?,
    val accelYg: Double?,
    val accelZg: Double?,
    val tempC: Double?,
    val humPct: Double?,
    val isAlert: Boolean,
    val alertReason: String?, // e.g. "ACCEL", "TEMP", "ACCEL,TEMP", or null
) {
    /** Individual alert reason codes, e.g. "ACCEL,TEMP" -> ["ACCEL", "TEMP"]. */
    val alertReasons: List<String>
        get() = alertReason?.split(",")?.filter { it.isNotBlank() } ?: emptyList()
}
