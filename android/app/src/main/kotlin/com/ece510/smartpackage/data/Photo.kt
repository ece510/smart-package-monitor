package com.ece510.smartpackage.data

/** One row from the Pi's PHOTOS listing (src/offline/bt_server.py, _list_photo_meta). */
data class PhotoMeta(
    val name: String,           // bare filename; the exact token passed back to PHOTO
    val kind: String,           // "reference" | "incident"
    val label: String?,         // "alarm_0s" etc. for incident photos, null for reference
    val sizeBytes: Int,
)

/** A fetched photo: its metadata plus the decoded JPEG bytes. */
data class PhotoData(
    val meta: PhotoMeta,
    val jpegBytes: ByteArray,
)
