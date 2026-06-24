package com.ece510.smartpackage.ui

import android.Manifest
import android.bluetooth.BluetoothDevice
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat

/**
 * Device picker + connection status. Lists only already-paired devices
 * (design point 4 — no in-app scanning) and walks the user through the
 * BLUETOOTH_CONNECT runtime permission (Android 12+) before listing them.
 */
@Composable
fun ConnectScreen(
    state: AppUiState,
    pairedDevicesProvider: () -> List<BluetoothDevice>,
    isBluetoothEnabled: () -> Boolean,
    onDeviceSelected: (BluetoothDevice) -> Unit,
) {
    val context = LocalContext.current

    var hasPermission by remember {
        mutableStateOf(hasBluetoothConnectPermission(context))
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasPermission = granted }

    LaunchedEffect(Unit) {
        if (!hasPermission && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissionLauncher.launch(Manifest.permission.BLUETOOTH_CONNECT)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Top,
    ) {
        Text("Trip History", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Connect to the package to see the trip history.",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(top = 8.dp, bottom = 16.dp),
        )

        when {
            !hasPermission -> StatusMessage(
                "Bluetooth permission is needed to continue.",
                action = { permissionLauncher.launch(Manifest.permission.BLUETOOTH_CONNECT) },
                actionLabel = "Grant permission",
            )

            !isBluetoothEnabled() -> StatusMessage(
                "Bluetooth is off. Turn it on from your phone's settings.",
            )

            state is AppUiState.Connecting -> LoadingMessage("Connecting to the package…")

            state is AppUiState.Downloading -> LoadingMessage("Downloading the trip history…")

            else -> {
                if (state is AppUiState.Error) {
                    StatusMessage(state.message)
                }

                val devices = pairedDevicesProvider()
                if (devices.isEmpty()) {
                    StatusMessage(
                        "No paired devices found. Pair the package from your phone's " +
                            "Bluetooth settings and reopen the app.",
                    )
                } else {
                    DeviceList(devices, onDeviceSelected)
                }
            }
        }
    }
}

@Composable
private fun DeviceList(
    devices: List<BluetoothDevice>,
    onDeviceSelected: (BluetoothDevice) -> Unit,
) {
    LazyColumn(modifier = Modifier.fillMaxWidth()) {
        items(devices) { device ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        runCatching { device.name }.getOrNull() ?: "Unnamed device",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(device.address, style = MaterialTheme.typography.bodySmall)
                    Button(
                        onClick = { onDeviceSelected(device) },
                        modifier = Modifier.padding(top = 8.dp),
                    ) {
                        Text("Connect and download")
                    }
                }
            }
        }
    }
}

@Composable
private fun LoadingMessage(text: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        CircularProgressIndicator(modifier = Modifier.padding(bottom = 12.dp))
        Text(text, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun StatusMessage(
    text: String,
    action: (() -> Unit)? = null,
    actionLabel: String? = null,
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.padding(bottom = 16.dp),
    ) {
        Text(text, style = MaterialTheme.typography.bodyLarge)
        if (action != null && actionLabel != null) {
            Button(onClick = action, modifier = Modifier.padding(top = 8.dp)) {
                Text(actionLabel)
            }
        }
    }
}

private fun hasBluetoothConnectPermission(context: android.content.Context): Boolean {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
    return ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.BLUETOOTH_CONNECT,
    ) == PackageManager.PERMISSION_GRANTED
}
