package com.ece510.smartpackage.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ece510.smartpackage.domain.AlertEvent
import com.ece510.smartpackage.domain.TripSummary
import com.ece510.smartpackage.domain.Verdict
import com.ece510.smartpackage.domain.reasonLabel
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * The destination screen: shows the whole trip at a glance — verdict,
 * key numbers, and the list of alert events — using only what the Pi
 * already decided (design point 7: no alert logic lives here).
 */
@Composable
fun HistoryScreen(
    summary: TripSummary,
    onRefresh: () -> Unit,
    onChooseAnotherDevice: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
        VerdictBanner(summary.verdict, summary.totalReadings)

        Row(modifier = Modifier.padding(top = 12.dp, bottom = 8.dp)) {
            Button(onClick = onRefresh) { Text("Actualizar") }
            Spacer(modifier = Modifier.padding(start = 8.dp))
            OutlinedButton(onClick = onChooseAnotherDevice) { Text("Otro dispositivo") }
        }

        if (summary.totalReadings == 0) {
            Text(
                "Sin datos del trayecto.",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(top = 16.dp),
            )
            return@Column
        }

        LazyColumn(modifier = Modifier.fillMaxWidth()) {
            item { SummaryCards(summary) }
            item {
                Text(
                    "Eventos detectados (${summary.alertEvents.size})",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 16.dp, bottom = 8.dp),
                )
            }
            if (summary.alertEvents.isEmpty()) {
                item { Text("Ninguna alerta durante el trayecto.") }
            } else {
                items(summary.alertEvents) { event -> AlertEventRow(event) }
            }
        }
    }
}

@Composable
private fun VerdictBanner(verdict: Verdict, totalReadings: Int) {
    val (label, color) = when (verdict) {
        Verdict.PACKAGE_OK -> "Package OK" to Color(0xFF2E7D32)
        Verdict.PROBLEMS_DETECTED -> "Problems detected" to Color(0xFFC62828)
        Verdict.NO_DATA -> "Sin datos del trayecto" to Color(0xFF616161)
    }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(color)
            .padding(16.dp),
    ) {
        Text(label, color = Color.White, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        if (totalReadings > 0) {
            Text("$totalReadings lecturas registradas", color = Color.White, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun SummaryCards(summary: TripSummary) {
    Column {
        InfoCard("Resumen") {
            Text("Lecturas totales: ${summary.totalReadings}")
            Text("Alertas totales: ${summary.totalAlerts}")
            summary.tripDuration?.let { duration ->
                Text("Duración del trayecto: ${formatDuration(duration)}")
            }
        }

        if (summary.alertBreakdown.isNotEmpty()) {
            InfoCard("Alertas por tipo") {
                summary.alertBreakdown.forEach { (code, count) ->
                    Text("${reasonLabel(code)}: $count")
                }
            }
        }

        if (summary.tempMinC != null || summary.humMinPct != null) {
            InfoCard("Sensores") {
                if (summary.tempMinC != null) {
                    Text("Temperatura: %.1f / %.1f / %.1f °C (mín/máx/media)".format(
                        summary.tempMinC, summary.tempMaxC, summary.tempMeanC,
                    ))
                } else {
                    Text("Sin datos de temperatura.")
                }
                if (summary.humMinPct != null) {
                    Text("Humedad: %.1f / %.1f / %.1f %% (mín/máx/media)".format(
                        summary.humMinPct, summary.humMaxPct, summary.humMeanPct,
                    ))
                } else {
                    Text("Sin datos de humedad.")
                }
                if (summary.maxNetAccelG != null) {
                    Text("Golpe más fuerte: %.2f g".format(summary.maxNetAccelG))
                } else {
                    Text("Sin datos de aceleración.")
                }
            }
        }
    }
}

@Composable
private fun InfoCard(title: String, content: @Composable () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(4.dp))
            content()
        }
    }
}

@Composable
private fun AlertEventRow(event: AlertEvent) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(formatLocalTime(event.ts), style = MaterialTheme.typography.bodySmall)
            Text(event.reasons.joinToString(", ") { reasonLabel(it) })
        }
    }
}

private val displayFormatter = DateTimeFormatter.ofPattern("dd/MM HH:mm:ss")

/** Converts the Pi's UTC ISO-8601 timestamp to the phone's local time for display. */
private fun formatLocalTime(ts: String): String =
    runCatching {
        OffsetDateTime.parse(ts)
            .atZoneSameInstant(ZoneId.systemDefault())
            .format(displayFormatter)
    }.getOrDefault(ts)

private fun formatDuration(duration: java.time.Duration): String {
    val totalSeconds = duration.seconds
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    return when {
        hours > 0 -> "%dh %02dm".format(hours, minutes)
        minutes > 0 -> "%dm %02ds".format(minutes, seconds)
        else -> "%ds".format(seconds)
    }
}
