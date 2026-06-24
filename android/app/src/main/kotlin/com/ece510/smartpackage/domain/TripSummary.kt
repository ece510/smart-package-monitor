package com.ece510.smartpackage.domain

import com.ece510.smartpackage.data.Reading
import java.time.Duration
import java.time.OffsetDateTime
import kotlin.math.sqrt

/** Overall outcome shown at the top of HistoryScreen. */
enum class Verdict { PACKAGE_OK, PROBLEMS_DETECTED, NO_DATA }

/** One alert row, kept separately for the event list in HistoryScreen. */
data class AlertEvent(
    val ts: String,
    val reasons: List<String>,
)

/**
 * One reading's worth of chart data, in trip order. Used by TripCharts.kt to
 * plot net acceleration / temperature / humidity over the trip — null fields
 * mean that reading didn't carry that sensor (e.g. a CV-only alert).
 */
data class TripPoint(
    val index: Int, // position in the ordered trip, used as the chart's X axis
    val ts: String,
    val netAccelG: Double?,
    val tempC: Double?,
    val humPct: Double?,
    val isAlert: Boolean,
)

/** Shock threshold in g, shared with the Pi's sensors.py ACCEL_NET_G_LIMIT so
 *  the chart's reference line matches what actually triggers an alert. */
const val NET_ACCEL_THRESHOLD_G = 0.3

/**
 * Descriptive statistics over a full trip's worth of [Reading]s. This is
 * pure Kotlin (no Android dependency) so it's unit-testable on the JVM —
 * see the design doc point 7: it never recomputes alerts, it only
 * summarizes what the Pi already decided via `is_alert`/`alert_reason`.
 */
data class TripSummary(
    val verdict: Verdict,
    val totalReadings: Int,
    val totalAlerts: Int,
    val alertBreakdown: Map<String, Int>, // e.g. {"ACCEL": 2, "CV": 1}
    val tempMinC: Double?,
    val tempMaxC: Double?,
    val tempMeanC: Double?,
    val humMinPct: Double?,
    val humMaxPct: Double?,
    val humMeanPct: Double?,
    val maxNetAccelG: Double?, // max of |sqrt(x^2+y^2+z^2) - 1.0| across readings
    val tripDuration: Duration?,
    val alertEvents: List<AlertEvent>,
    val series: List<TripPoint>,
)

object TripSummaryCalculator {

    /** Builds a [TripSummary] from a trip's readings, in any order. */
    fun summarize(readings: List<Reading>): TripSummary {
        if (readings.isEmpty()) {
            return TripSummary(
                verdict = Verdict.NO_DATA,
                totalReadings = 0,
                totalAlerts = 0,
                alertBreakdown = emptyMap(),
                tempMinC = null, tempMaxC = null, tempMeanC = null,
                humMinPct = null, humMaxPct = null, humMeanPct = null,
                maxNetAccelG = null,
                tripDuration = null,
                alertEvents = emptyList(),
                series = emptyList(),
            )
        }

        val ordered = readings.sortedBy { it.id }
        val alertRows = ordered.filter { it.isAlert }

        val breakdown = mutableMapOf<String, Int>()
        for (row in alertRows) {
            for (reason in row.alertReasons) {
                breakdown[reason] = (breakdown[reason] ?: 0) + 1
            }
        }

        val temps = ordered.mapNotNull { it.tempC }
        val hums = ordered.mapNotNull { it.humPct }
        val netAccels = ordered.mapNotNull { netAcceleration(it) }

        return TripSummary(
            verdict = if (alertRows.isNotEmpty()) Verdict.PROBLEMS_DETECTED else Verdict.PACKAGE_OK,
            totalReadings = ordered.size,
            totalAlerts = alertRows.size,
            alertBreakdown = breakdown,
            tempMinC = temps.minOrNull(),
            tempMaxC = temps.maxOrNull(),
            tempMeanC = temps.average().takeIf { temps.isNotEmpty() },
            humMinPct = hums.minOrNull(),
            humMaxPct = hums.maxOrNull(),
            humMeanPct = hums.average().takeIf { hums.isNotEmpty() },
            maxNetAccelG = netAccels.maxOrNull(),
            tripDuration = tripDuration(ordered),
            alertEvents = alertRows.map { AlertEvent(it.ts, it.alertReasons) },
            series = ordered.mapIndexed { i, r ->
                TripPoint(
                    index = i,
                    ts = r.ts,
                    netAccelG = netAcceleration(r),
                    tempC = r.tempC,
                    humPct = r.humPct,
                    isAlert = r.isAlert,
                )
            },
        )
    }

    /**
     * Acceleration magnitude minus gravity: sqrt(x^2+y^2+z^2) - 1.0, in g.
     * At rest the magnitude is ~1.0g (gravity on whichever axis is
     * "down"), so subtracting it isolates the component caused by an
     * actual shock/impact rather than orientation (design point 8).
     * Returns null if any axis reading is missing (e.g. a CV-only alert).
     */
    fun netAcceleration(reading: Reading): Double? {
        val x = reading.accelXg ?: return null
        val y = reading.accelYg ?: return null
        val z = reading.accelZg ?: return null
        val magnitude = sqrt(x * x + y * y + z * z)
        return kotlin.math.abs(magnitude - 1.0)
    }

    /** Wall-clock span between the first and last reading's timestamps. */
    private fun tripDuration(ordered: List<Reading>): Duration? {
        val first = parseTimestamp(ordered.first().ts) ?: return null
        val last = parseTimestamp(ordered.last().ts) ?: return null
        return Duration.between(first, last).abs()
    }

    private fun parseTimestamp(ts: String) =
        runCatching { OffsetDateTime.parse(ts).toInstant() }.getOrNull()
}

/** Human-readable label for a single alert reason code, for the UI. */
fun reasonLabel(code: String): String = when (code) {
    "ACCEL" -> "Golpe / impacto"
    "TEMP" -> "Temperatura fuera de rango"
    "HUM" -> "Humedad anómala"
    "CV" -> "Manipulación detectada por cámara"
    else -> code
}
