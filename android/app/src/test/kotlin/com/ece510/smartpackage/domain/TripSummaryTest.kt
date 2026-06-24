package com.ece510.smartpackage.domain

import com.ece510.smartpackage.data.Reading
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Same three rows seeded by tests/test_bt_forward.py, expressed directly as [Reading]s. */
class TripSummaryTest {

    private val normal = Reading(
        id = 1, ts = "2026-06-24T10:00:00.000000+00:00",
        accelXg = 0.02, accelYg = -0.01, accelZg = 0.98,
        tempC = 21.4, humPct = 38.2,
        isAlert = false, alertReason = null,
    )

    private val accelAlert = Reading(
        id = 2, ts = "2026-06-24T10:02:00.000000+00:00",
        accelXg = 0.85, accelYg = 0.02, accelZg = 1.10,
        tempC = 22.0, humPct = 40.0,
        isAlert = true, alertReason = "ACCEL",
    )

    // Vision-only alert: no sensor values attached, same as a CV row in store.py.
    private val cvAlert = Reading(
        id = 3, ts = "2026-06-24T10:05:00.000000+00:00",
        accelXg = null, accelYg = null, accelZg = null,
        tempC = null, humPct = null,
        isAlert = true, alertReason = "CV",
    )

    private val DELTA = 1e-3

    @Test
    fun `verdict is PROBLEMS_DETECTED when any reading is flagged by the Pi`() {
        val summary = TripSummaryCalculator.summarize(listOf(normal, accelAlert, cvAlert))

        assertEquals(Verdict.PROBLEMS_DETECTED, summary.verdict)
    }

    @Test
    fun `verdict is PACKAGE_OK when no reading is flagged`() {
        val summary = TripSummaryCalculator.summarize(listOf(normal))

        assertEquals(Verdict.PACKAGE_OK, summary.verdict)
    }

    @Test
    fun `verdict is NO_DATA for an empty trip`() {
        val summary = TripSummaryCalculator.summarize(emptyList())

        assertEquals(Verdict.NO_DATA, summary.verdict)
        assertEquals(0, summary.totalReadings)
        assertTrue(summary.alertEvents.isEmpty())
    }

    @Test
    fun `counts and breakdown match the seeded rows`() {
        val summary = TripSummaryCalculator.summarize(listOf(normal, accelAlert, cvAlert))

        assertEquals(3, summary.totalReadings)
        assertEquals(2, summary.totalAlerts)
        assertEquals(mapOf("ACCEL" to 1, "CV" to 1), summary.alertBreakdown)
    }

    @Test
    fun `temperature and humidity stats ignore readings with no sensor values`() {
        val summary = TripSummaryCalculator.summarize(listOf(normal, accelAlert, cvAlert))

        assertEquals(21.4, summary.tempMinC!!, DELTA)
        assertEquals(22.0, summary.tempMaxC!!, DELTA)
        assertEquals(21.7, summary.tempMeanC!!, DELTA)
        assertEquals(38.2, summary.humMinPct!!, DELTA)
        assertEquals(40.0, summary.humMaxPct!!, DELTA)
        assertEquals(39.1, summary.humMeanPct!!, DELTA)
    }

    @Test
    fun `net acceleration strips gravity and picks the largest shock`() {
        // normal: sqrt(0.02^2+0.01^2+0.98^2) ~= 0.9803 -> net ~= 0.0197
        // accelAlert: sqrt(0.85^2+0.02^2+1.10^2) ~= 1.3903 -> net ~= 0.3903 (the shock)
        val summary = TripSummaryCalculator.summarize(listOf(normal, accelAlert, cvAlert))

        assertEquals(0.3903, summary.maxNetAccelG!!, 1e-3)
    }

    @Test
    fun `net acceleration is null when any axis is missing`() {
        assertNull(TripSummaryCalculator.netAcceleration(cvAlert))
    }

    @Test
    fun `trip duration spans the first to the last reading`() {
        val summary = TripSummaryCalculator.summarize(listOf(normal, accelAlert, cvAlert))

        assertEquals(5 * 60L, summary.tripDuration!!.seconds)
    }

    @Test
    fun `trip duration is order-independent (readings sorted by id)`() {
        val summary = TripSummaryCalculator.summarize(listOf(cvAlert, normal, accelAlert))

        assertEquals(5 * 60L, summary.tripDuration!!.seconds)
    }

    @Test
    fun `alert events list carries timestamp and reasons in id order`() {
        val summary = TripSummaryCalculator.summarize(listOf(normal, accelAlert, cvAlert))

        assertEquals(
            listOf(
                AlertEvent(accelAlert.ts, listOf("ACCEL")),
                AlertEvent(cvAlert.ts, listOf("CV")),
            ),
            summary.alertEvents,
        )
    }

    @Test
    fun `series has one point per reading ordered by id with matching net acceleration`() {
        // Built from cvAlert, normal, accelAlert passed out of order, same as the
        // duration test above — series must still come out sorted by id.
        val summary = TripSummaryCalculator.summarize(listOf(cvAlert, normal, accelAlert))

        assertEquals(3, summary.series.size)
        assertEquals(listOf(0, 1, 2), summary.series.map { it.index })
        assertEquals(listOf(normal.ts, accelAlert.ts, cvAlert.ts), summary.series.map { it.ts })

        val normalPoint = summary.series[0]
        assertEquals(0.0197, normalPoint.netAccelG!!, 1e-3)
        assertEquals(21.4, normalPoint.tempC!!, DELTA)
        assertEquals(38.2, normalPoint.humPct!!, DELTA)
        assertEquals(false, normalPoint.isAlert)

        val cvPoint = summary.series[2]
        assertNull(cvPoint.netAccelG)
        assertNull(cvPoint.tempC)
        assertEquals(true, cvPoint.isAlert)
    }

    @Test
    fun `series is empty for a trip with no data`() {
        val summary = TripSummaryCalculator.summarize(emptyList())

        assertTrue(summary.series.isEmpty())
    }

    @Test
    fun `reasonLabel translates known codes and falls back to the raw code`() {
        assertEquals("Shock / impact", reasonLabel("ACCEL"))
        assertEquals("Temperature out of range", reasonLabel("TEMP"))
        assertEquals("Abnormal humidity", reasonLabel("HUM"))
        assertEquals("Tampering detected by camera", reasonLabel("CV"))
        assertEquals("WEIRD", reasonLabel("WEIRD"))
    }
}
