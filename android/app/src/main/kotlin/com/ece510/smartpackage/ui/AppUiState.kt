package com.ece510.smartpackage.ui

import com.ece510.smartpackage.domain.TripSummary

/**
 * Screen-level state machine: Idle -> Connecting -> Downloading ->
 * Loaded/Error (design doc, MainActivity + ViewModel section).
 */
sealed interface AppUiState {
    /** Showing the device picker, nothing attempted yet. */
    data object Idle : AppUiState

    /** Opening the RFCOMM socket to the chosen device. */
    data object Connecting : AppUiState

    /** Socket open; sent `ALL` and waiting for the full reply. */
    data object Downloading : AppUiState

    /** Trip parsed and summarized successfully. */
    data class Loaded(val summary: TripSummary) : AppUiState

    /** Anything that went wrong, with a message fit to show the user directly. */
    data class Error(val message: String) : AppUiState
}
