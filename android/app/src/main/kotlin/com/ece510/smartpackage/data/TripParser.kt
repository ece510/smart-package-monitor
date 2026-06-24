package com.ece510.smartpackage.data

import org.json.JSONException
import org.json.JSONObject

/**
 * Parses the line-based response of the Pi's `ALL` command (see
 * src/offline/bt_server.py): a banner line, then one JSON object per
 * reading, then a final `{"done": N}` line. Robust against the things a
 * live RFCOMM stream can throw at it — the banner, the trailer, and any
 * truncated/garbled line — without ever throwing (point 12 of the design:
 * the app must show a clear message, never crash).
 */
object TripParser {

    /**
     * Parses raw lines (already split on '\n') into a list of [Reading].
     * Lines that aren't a reading object (banner, `{"done": ...}`, blank,
     * or malformed JSON) are silently skipped.
     */
    fun parseLines(lines: List<String>): List<Reading> =
        lines.mapNotNull { parseLine(it) }

    private fun parseLine(rawLine: String): Reading? {
        val line = rawLine.trim()
        if (line.isEmpty() || !line.startsWith("{")) return null

        return try {
            val obj = JSONObject(line)
            // Only object with an "id" field is a reading row; the banner
            // is plain text and the trailer is {"done": N} with no "id".
            if (!obj.has("id")) return null

            Reading(
                id = obj.getInt("id"),
                ts = obj.getString("ts"),
                accelXg = obj.optDoubleOrNull("accel_x_g"),
                accelYg = obj.optDoubleOrNull("accel_y_g"),
                accelZg = obj.optDoubleOrNull("accel_z_g"),
                tempC = obj.optDoubleOrNull("temp_c"),
                humPct = obj.optDoubleOrNull("hum_pct"),
                isAlert = obj.optBoolean("is_alert", false),
                alertReason = if (obj.isNull("alert_reason")) null
                              else obj.optString("alert_reason", null),
            )
        } catch (_: JSONException) {
            null
        }
    }

    /** True once a line is the `{"done": N}` trailer that ends an ALL/SYNC response. */
    fun isDoneLine(rawLine: String): Boolean {
        val line = rawLine.trim()
        if (!line.startsWith("{")) return false
        return try {
            JSONObject(line).has("done")
        } catch (_: JSONException) {
            false
        }
    }

    private fun JSONObject.optDoubleOrNull(key: String): Double? =
        if (isNull(key) || !has(key)) null else optDouble(key).takeIf { !it.isNaN() }
}
