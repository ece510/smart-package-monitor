package com.ece510.smartpackage.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ece510.smartpackage.domain.NET_ACCEL_THRESHOLD_G
import com.ece510.smartpackage.domain.TripPoint

/**
 * Trip charts shown on HistoryScreen, between the summary cards and the alert
 * event list — lets the user see "the path" the package took and where a
 * problem happened, instead of only mín/máx/media numbers.
 *
 * Drawn with plain Compose [Canvas] (no chart library dependency): Vico
 * 2.0.2's artifacts are compiled against Kotlin 2.1 metadata, which this
 * project's Kotlin 1.9.24 compiler can't read (verified via assembleDebug —
 * "incompatible version of Kotlin" errors). Bumping the whole Kotlin/Compose
 * toolchain right before the demo was judged too risky, so this is the
 * planned fallback, not a placeholder.
 *
 * Each chart plots one metric across the trip's [TripPoint]s, skipping
 * readings where that metric is null (e.g. a CV-only alert has no sensor
 * values). A chart is omitted entirely if it would have no points to show.
 *
 * The net-acceleration chart additionally draws a dashed reference line at
 * [NET_ACCEL_THRESHOLD_G] and marks points above it in red — those are
 * exactly the readings the Pi flagged as ACCEL alerts (sensors.py uses the
 * same threshold), so the crossing itself shows "where the problem was".
 */
@Composable
fun TripCharts(series: List<TripPoint>) {
    Column(modifier = Modifier.fillMaxWidth()) {
        NetAccelChart(series)
        MetricChart(
            title = "Temperatura (°C)",
            points = series.mapNotNull { p -> p.tempC },
        )
        MetricChart(
            title = "Humedad (%)",
            points = series.mapNotNull { p -> p.humPct },
        )
    }
}

@Composable
private fun NetAccelChart(series: List<TripPoint>) {
    val points = series.mapNotNull { p -> p.netAccelG }
    if (points.isEmpty()) return

    ChartCard(title = "Aceleración neta (g) — línea punteada = umbral de golpe") {
        LineChartCanvas(
            values = points,
            thresholds = points.map { NET_ACCEL_THRESHOLD_G },
            highlight = { value -> value > NET_ACCEL_THRESHOLD_G },
        )
    }
}

@Composable
private fun MetricChart(title: String, points: List<Double>) {
    if (points.isEmpty()) return

    ChartCard(title = title) {
        LineChartCanvas(values = points)
    }
}

/**
 * Minimal line chart: scales [values] to fill the canvas, draws them as a
 * polyline, optionally a dashed reference line ([thresholds], same length as
 * [values]) and red dots on points where [highlight] is true.
 */
@Composable
private fun LineChartCanvas(
    values: List<Double>,
    thresholds: List<Double>? = null,
    highlight: (Double) -> Boolean = { false },
) {
    val lineColor = MaterialTheme.colorScheme.primary
    val thresholdColor = MaterialTheme.colorScheme.outline
    val alertColor = Color(0xFFC62828)

    Canvas(modifier = Modifier.fillMaxWidth().height(140.dp)) {
        if (values.size < 2) return@Canvas

        val allValues = if (thresholds != null) values + thresholds else values
        val minV = allValues.min()
        val maxV = allValues.max()
        val range = (maxV - minV).takeIf { it > 0.0 } ?: 1.0

        val stepX = size.width / (values.size - 1)
        fun pointAt(i: Int, value: Double): Offset {
            val x = i * stepX
            val y = size.height - ((value - minV) / range * size.height).toFloat()
            return Offset(x, y)
        }

        thresholds?.let { th ->
            val path = th.mapIndexed { i, v -> pointAt(i, v) }
            for (i in 0 until path.size - 1) {
                drawLine(
                    color = thresholdColor,
                    start = path[i],
                    end = path[i + 1],
                    strokeWidth = 2f,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)),
                )
            }
        }

        val linePoints = values.mapIndexed { i, v -> pointAt(i, v) }
        for (i in 0 until linePoints.size - 1) {
            drawLine(
                color = lineColor,
                start = linePoints[i],
                end = linePoints[i + 1],
                strokeWidth = 3f,
            )
        }

        values.forEachIndexed { i, v ->
            if (highlight(v)) {
                drawCircle(color = alertColor, radius = 5f, center = linePoints[i])
            }
        }
    }
}

@Composable
private fun ChartCard(title: String, content: @Composable () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            content()
        }
    }
}
