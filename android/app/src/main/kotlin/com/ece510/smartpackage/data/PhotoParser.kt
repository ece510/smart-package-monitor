package com.ece510.smartpackage.data

import org.json.JSONException
import org.json.JSONObject
import java.util.Base64

/**
 * Parses the line-based responses of the Pi's PHOTOS/PHOTO commands (see
 * src/offline/bt_server.py: _list_photo_meta, _send_photo). Same robustness
 * stance as TripParser — never throws, skips anything that isn't the shape
 * it expects (banner, trailer, unrelated replies).
 *
 * Uses java.util.Base64 (JDK, available since API 26) rather than
 * android.util.Base64: the latter is a stub in plain JVM unit tests
 * (throws "not mocked" without Robolectric), and minSdk is 31 here, so the
 * JDK class is safe to use directly on-device too.
 */
object PhotoParser {

    /** Parses a PHOTOS listing: banner, then one {"name": ...} row per photo,
     * then {"done": N}. The banner/trailer are skipped because they have no
     * "name" key. */
    fun parseList(lines: List<String>): List<PhotoMeta> =
        lines.mapNotNull { parsePhotoMeta(it) }

    private fun parsePhotoMeta(rawLine: String): PhotoMeta? {
        val line = rawLine.trim()
        if (line.isEmpty() || !line.startsWith("{")) return null
        return try {
            val obj = JSONObject(line)
            if (!obj.has("name")) return null
            PhotoMeta(
                name = obj.getString("name"),
                kind = obj.optString("kind", "incident"),
                label = if (obj.isNull("label") || !obj.has("label")) null else obj.optString("label", null),
                sizeBytes = obj.optInt("size", 0),
            )
        } catch (_: JSONException) {
            null
        }
    }

    /**
     * Parses a PHOTO reply: header {"photo": ...}, then the base64 payload
     * line, then {"done": 1}. Returns null if no payload line is present
     * (truncated transfer) or if it fails to decode.
     */
    fun parsePhoto(meta: PhotoMeta, lines: List<String>): ByteArray? {
        val payload = lines.firstOrNull { it.isNotBlank() && !it.trim().startsWith("{") }
            ?: return null
        return try {
            Base64.getDecoder().decode(payload.trim())
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    /**
     * Parses an ALLPHOTOS reply: zero or more {"photo": ..., "kind": ...,
     * "label": ...} headers each immediately followed by a base64 payload
     * line, then a single trailing {"done": N}. Unlike [parseList]/[parsePhoto]
     * (which assume one photo per request), this walks the whole stream
     * pairing each header with the line right after it. A header whose next
     * line is missing or fails to decode is skipped rather than aborting the
     * rest of the batch — consistent with this object's "never throws, skip
     * what doesn't fit" stance.
     */
    fun parseAll(lines: List<String>): List<PhotoData> {
        val photos = mutableListOf<PhotoData>()
        var i = 0
        while (i < lines.size) {
            val header = parsePhotoHeader(lines[i])
            if (header == null) {
                i++
                continue
            }
            val payloadLine = lines.getOrNull(i + 1)
            val bytes = payloadLine?.trim()?.let { payload ->
                try {
                    Base64.getDecoder().decode(payload)
                } catch (_: IllegalArgumentException) {
                    null
                }
            }
            if (bytes != null) {
                photos.add(PhotoData(header, bytes))
            }
            i += 2
        }
        return photos
    }

    private fun parsePhotoHeader(rawLine: String): PhotoMeta? {
        val line = rawLine.trim()
        if (line.isEmpty() || !line.startsWith("{")) return null
        return try {
            val obj = JSONObject(line)
            if (!obj.has("photo")) return null
            PhotoMeta(
                name = obj.getString("photo"),
                kind = obj.optString("kind", "incident"),
                label = if (obj.isNull("label") || !obj.has("label")) null else obj.optString("label", null),
                sizeBytes = obj.optInt("size", 0),
            )
        } catch (_: JSONException) {
            null
        }
    }

    /** True if the reply was a single {"error": ...} line rather than a photo. */
    fun errorMessage(lines: List<String>): String? =
        lines.mapNotNull { rawLine ->
            val line = rawLine.trim()
            if (!line.startsWith("{")) return@mapNotNull null
            try {
                val obj = JSONObject(line)
                if (obj.has("error")) obj.getString("error") else null
            } catch (_: JSONException) {
                null
            }
        }.firstOrNull()
}
