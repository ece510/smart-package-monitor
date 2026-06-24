package com.ece510.smartpackage.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ece510.smartpackage.domain.AlertEvent
import com.ece510.smartpackage.domain.TripSummary
import com.ece510.smartpackage.domain.reasonColor
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
    onClearHistory: () -> Unit,
    onViewPhotos: () -> Unit,
) {
    var showClearConfirm by remember { mutableStateOf(false) }

    if (showClearConfirm) {
        AlertDialog(
            onDismissRequest = { showClearConfirm = false },
            title = { Text("Clear trip history?") },
            text = { Text("This will permanently delete all stored readings from the package.") },
            confirmButton = {
                TextButton(onClick = {
                    showClearConfirm = false
                    onClearHistory()
                }) { Text("Clear") }
            },
            dismissButton = {
                TextButton(onClick = { showClearConfirm = false }) { Text("Cancel") }
            },
        )
    }

    Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
        VerdictBanner(summary.verdict, summary.totalReadings)

        Row(
            modifier = Modifier
                .padding(top = 12.dp, bottom = 8.dp)
                .horizontalScroll(rememberScrollState()),
        ) {
            Button(onClick = onRefresh) { Text("Refresh") }
            Spacer(modifier = Modifier.padding(start = 8.dp))
            OutlinedButton(onClick = onViewPhotos) { Text("Photos") }
            Spacer(modifier = Modifier.padding(start = 8.dp))
            OutlinedButton(onClick = onChooseAnotherDevice) { Text("Another device") }
            Spacer(modifier = Modifier.padding(start = 8.dp))
            OutlinedButton(onClick = { showClearConfirm = true }) { Text("Clear history") }
        }

        if (summary.totalReadings == 0) {
            Text(
                "No trip data.",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.padding(top = 16.dp),
            )
            return@Column
        }

        LazyColumn(modifier = Modifier.fillMaxWidth()) {
            item { SummaryCards(summary) }
            item { TripCharts(summary.series) }
            item {
                Text(
                    "Detected events (${summary.alertEvents.size})",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 16.dp, bottom = 8.dp),
                )
            }
            if (summary.alertEvents.isEmpty()) {
                item { Text("No alerts during the trip.") }
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
        Verdict.NO_DATA -> "No trip data" to Color(0xFF616161)
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
            Text("$totalReadings readings recorded", color = Color.White, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun SummaryCards(summary: TripSummary) {
    Column {
        InfoCard("Summary") {
            Text("Total readings: ${summary.totalReadings}")
            Text("Total alerts: ${summary.totalAlerts}")
            summary.tripDuration?.let { duration ->
                Text("Trip duration: ${formatDuration(duration)}")
            }
        }

        if (summary.alertBreakdown.isNotEmpty()) {
            InfoCard("Alerts by type") {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    summary.alertBreakdown.forEach { (code, count) ->
                        AlertChip(code, count)
                    }
                }
            }
        }

        if (summary.tempMinC != null || summary.humMinPct != null) {
            InfoCard("Sensors") {
                if (summary.tempMinC != null) {
                    Text("Temperature: %.1f / %.1f / %.1f °C (min/max/mean)".format(
                        summary.tempMinC, summary.tempMaxC, summary.tempMeanC,
                    ))
                } else {
                    Text("No temperature data.")
                }
                if (summary.humMinPct != null) {
                    Text("Humidity: %.1f / %.1f / %.1f %% (min/max/mean)".format(
                        summary.humMinPct, summary.humMaxPct, summary.humMeanPct,
                    ))
                } else {
                    Text("No humidity data.")
                }
                if (summary.maxNetAccelG != null) {
                    Text("Strongest shock: %.2f g".format(summary.maxNetAccelG))
                } else {
                    Text("No acceleration data.")
                }
            }
        }
    }
}

@Composable
private fun AlertChip(code: String, count: Int) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(16.dp))
            .background(reasonColor(code))
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("${reasonLabel(code)}: $count", color = Color.White, style = MaterialTheme.typography.labelLarge)
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
