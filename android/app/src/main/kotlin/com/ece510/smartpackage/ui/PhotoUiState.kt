package com.ece510.smartpackage.ui

import com.ece510.smartpackage.data.PhotoData

/**
 * State machine for the "Photos" panel, kept separate from [AppUiState]:
 * browsing photos is a logically independent flow layered on top of the
 * loaded trip view, with its own connect/fetch cycle, so it shouldn't fold
 * into (or discard) the main trip state.
 */
sealed interface PhotoUiState {
    /** Photo panel closed. */
    data object Hidden : PhotoUiState

    /** Fetching the PHOTOS listing. */
    data object LoadingList : PhotoUiState

    /** All photos already downloaded and decoded in one ALLPHOTOS session;
     * [selected] non-null while one photo is open (a local, network-free
     * pick from [photos] — see TripViewModel.selectPhoto()). */
    data class ListLoaded(
        val photos: List<PhotoData>,
        val selected: PhotoData? = null,
    ) : PhotoUiState

    /** A list- or fetch-level failure, with a user-facing message. */
    data class Error(val message: String) : PhotoUiState
}
