package com.ece510.smartpackage.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import com.ece510.smartpackage.data.PhotoData
import com.ece510.smartpackage.data.PhotoMeta

/**
 * Photo browser, reached from HistoryScreen's "Photos" button. Renders
 * [PhotoUiState] as a list of already-downloaded photos (fetched up front
 * in one ALLPHOTOS session — see TripViewModel.openPhotos()), or the
 * currently selected one. Network state lives in TripViewModel.photoState,
 * separate from the main trip's AppUiState (see PhotoUiState.kt).
 */
@Composable
fun PhotosPanel(
    state: PhotoUiState,
    onSelect: (PhotoData) -> Unit,
    onClosePhoto: () -> Unit,
    onClosePanel: () -> Unit,
    onRetryList: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
        Row {
            Text("Photos", style = MaterialTheme.typography.headlineSmall)
            Spacer(modifier = Modifier.weight(1f))
            OutlinedButton(onClick = onClosePanel) { Text("Back to trip") }
        }
        Spacer(modifier = Modifier.height(12.dp))

        when (state) {
            is PhotoUiState.LoadingList -> CenterText("Loading photo list…")
            is PhotoUiState.Error -> Column {
                Text(state.message, color = MaterialTheme.colorScheme.error)
                Spacer(modifier = Modifier.height(8.dp))
                Button(onClick = onRetryList) { Text("Try again") }
            }
            is PhotoUiState.ListLoaded -> {
                val selected = state.selected
                if (selected != null) {
                    PhotoViewer(selected, onClosePhoto)
                } else if (state.photos.isEmpty()) {
                    CenterText("No photos available yet.")
                } else {
                    LazyColumn(modifier = Modifier.fillMaxWidth()) {
                        items(state.photos) { photo ->
                            PhotoRow(
                                meta = photo.meta,
                                onClick = { onSelect(photo) },
                            )
                        }
                    }
                }
            }
            PhotoUiState.Hidden -> { /* not rendered */ }
        }
    }
}

@Composable
private fun PhotoRow(meta: PhotoMeta, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(captionFor(meta), style = MaterialTheme.typography.titleMedium)
                Text(
                    "%.0f KB".format(meta.sizeBytes / 1024.0),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            // No fetch in flight to guard against here: all photos were
            // already downloaded by openPhotos(), so "View" just selects
            // bytes already in memory — no Bluetooth involved.
            Button(onClick = onClick) { Text("View") }
        }
    }
}

@Composable
private fun PhotoViewer(photo: PhotoData, onClose: () -> Unit) {
    val bmp = remember(photo) {
        BitmapFactory.decodeByteArray(photo.jpegBytes, 0, photo.jpegBytes.size)
    }
    Column(modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = onClose) { Text("Back to list") }
        Spacer(modifier = Modifier.height(8.dp))
        if (bmp != null) {
            Image(
                bitmap = bmp.asImageBitmap(),
                contentDescription = captionFor(photo.meta),
                modifier = Modifier.fillMaxWidth(),
                contentScale = ContentScale.FillWidth,
            )
        } else {
            Text("Could not decode this image.", color = MaterialTheme.colorScheme.error)
        }
    }
}

private fun captionFor(meta: PhotoMeta): String = when {
    meta.kind == "reference" -> "Reference photo (at setup)"
    meta.label == "alarm_0s" -> "Incident — 0s"
    meta.label == "alarm_5s" -> "Incident — 5s"
    meta.label == "alarm_10s" -> "Incident — 10s"
    meta.label == "shutdown_4th" -> "Incident — final"
    else -> meta.name
}

@Composable
private fun CenterText(text: String) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text(text)
    }
}
