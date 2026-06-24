package com.ece510.smartpackage

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import com.ece510.smartpackage.ui.AppUiState
import com.ece510.smartpackage.ui.ConnectScreen
import com.ece510.smartpackage.ui.HistoryScreen
import com.ece510.smartpackage.ui.PhotoUiState
import com.ece510.smartpackage.ui.PhotosPanel
import com.ece510.smartpackage.ui.TripViewModel

class MainActivity : ComponentActivity() {

    private val viewModel: TripViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val state by viewModel.uiState.collectAsState()
                    val photoState by viewModel.photoState.collectAsState()

                    when (val current = state) {
                        is AppUiState.Loaded -> {
                            if (photoState !is PhotoUiState.Hidden) {
                                PhotosPanel(
                                    state = photoState,
                                    onSelect = { viewModel.selectPhoto(it) },
                                    onClosePhoto = { viewModel.closePhoto() },
                                    onClosePanel = { viewModel.closePhotos() },
                                    onRetryList = { viewModel.openPhotos() },
                                )
                            } else {
                                HistoryScreen(
                                    summary = current.summary,
                                    onRefresh = { viewModel.refresh() },
                                    onChooseAnotherDevice = { viewModel.reset() },
                                    onClearHistory = { viewModel.clearHistory() },
                                    onViewPhotos = { viewModel.openPhotos() },
                                )
                            }
                        }

                        else -> ConnectScreen(
                            state = current,
                            pairedDevicesProvider = { viewModel.pairedDevices() },
                            isBluetoothEnabled = { viewModel.isBluetoothEnabled() },
                            onDeviceSelected = { device -> viewModel.connectAndDownload(device) },
                        )
                    }
                }
            }
        }
    }
}
