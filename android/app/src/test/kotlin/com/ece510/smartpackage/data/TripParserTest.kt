package com.ece510.smartpackage.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Mirrors the rows seeded by tests/test_bt_forward.py on the Pi side, plus
 * the surrounding banner/trailer lines a real SPP session sends for `ALL`.
 */
class TripParserTest {

    private val bannerLine = "SPM-BT ready | commands: STATUS, SYNC, ALL, CLEAR"

    private val normalLine =
        """{"id": 1, "ts": "2026-06-24T10:00:00.000000+00:00", "accel_x_g": 0.02, """ +
        """"accel_y_g": -0.01, "accel_z_g": 0.98, "temp_c": 21.4, "hum_pct": 38.2, """ +
        """"is_alert": false, "alert_reason": null}"""

    private val accelAlertLine =
        """{"id": 2, "ts": "2026-06-24T10:02:00.000000+00:00", "accel_x_g": 0.85, """ +
        """"accel_y_g": 0.02, "accel_z_g": 1.10, "temp_c": 22.0, "hum_pct": 40.0, """ +
        """"is_alert": true, "alert_reason": "ACCEL"}"""

    // CV alert: vision-only, no sensor values attached (store.py allows this).
    private val cvAlertLine =
        """{"id": 3, "ts": "2026-06-24T10:05:00.000000+00:00", "accel_x_g": null, """ +
        """"accel_y_g": null, "accel_z_g": null, "temp_c": null, "hum_pct": null, """ +
        """"is_alert": true, "alert_reason": "CV"}"""

    private val doneLine = """{"done": 3}"""

    @Test
    fun `parses a full ALL response into three readings, skipping banner and trailer`() {
        val lines = listOf(bannerLine, normalLine, accelAlertLine, cvAlertLine, doneLine)

        val readings = TripParser.parseLines(lines)

        assertEquals(3, readings.size)
        assertEquals(listOf(1, 2, 3), readings.map { it.id })
    }

    @Test
    fun `normal reading has all sensor fields and no alert`() {
        val reading = TripParser.parseLines(listOf(normalLine)).single()

        assertEquals(0.02, reading.accelXg)
        assertEquals(21.4, reading.tempC)
        assertEquals(38.2, reading.humPct)
        assertFalse(reading.isAlert)
        assertNull(reading.alertReason)
        assertTrue(reading.alertReasons.isEmpty())
    }

    @Test
    fun `CV alert has no sensor values but is flagged as an alert`() {
        val reading = TripParser.parseLines(listOf(cvAlertLine)).single()

        assertNull(reading.accelXg)
        assertNull(reading.tempC)
        assertTrue(reading.isAlert)
        assertEquals(listOf("CV"), reading.alertReasons)
    }

    @Test
    fun `combined alert reasons split correctly`() {
        val combined = normalLine.replace(
            """"is_alert": false, "alert_reason": null""",
            """"is_alert": true, "alert_reason": "ACCEL,TEMP""""
        )

        val reading = TripParser.parseLines(listOf(combined)).single()

        assertEquals(listOf("ACCEL", "TEMP"), reading.alertReasons)
    }

    @Test
    fun `malformed and unrelated lines are skipped without throwing`() {
        val garbled = """{"id": 4, "ts": "2026-06-24T10:06""" // truncated mid-stream
        val blank = ""
        val notAReading = """{"pending": 1, "total": 3}""" // a STATUS reply, not a row

        val readings = TripParser.parseLines(
            listOf(bannerLine, garbled, blank, notAReading, normalLine, doneLine)
        )

        assertEquals(1, readings.size)
        assertEquals(1, readings.single().id)
    }

    @Test
    fun `empty response (no rows) parses to an empty list`() {
        val readings = TripParser.parseLines(listOf(bannerLine, doneLine))

        assertTrue(readings.isEmpty())
    }

    @Test
    fun `isDoneLine recognizes only the trailer`() {
        assertTrue(TripParser.isDoneLine(doneLine))
        assertFalse(TripParser.isDoneLine(normalLine))
        assertFalse(TripParser.isDoneLine(bannerLine))
    }
}
