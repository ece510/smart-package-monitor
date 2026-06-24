package com.ece510.smartpackage.data

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Mirrors the PHOTOS/PHOTO line protocol implemented by
 * src/offline/bt_server.py (_list_photo_meta, _send_photo).
 */
class PhotoParserTest {

    private val bannerLine = "SPM-BT ready | commands: STATUS, SYNC, ALL, CLEAR, RESET, PHOTOS, PHOTO"

    private val referenceRow =
        """{"name": "reference_frame_detected.jpg", "kind": "reference", "size": 84213}"""

    private val incidentRow =
        """{"name": "capture_alarm_0s_20260624-101500.jpg", "kind": "incident", "label": "alarm_0s", "size": 142880}"""

    private val doneLine = """{"done": 2}"""

    // base64.b64encode(b"FAKE_JPEG_BYTES") computed on the Pi side.
    private val fakeJpegBytes = "FAKE_JPEG_BYTES".toByteArray(Charsets.US_ASCII)
    private val fakeJpegBase64 = "RkFLRV9KUEVHX0JZVEVT"

    private val photoMeta = PhotoMeta(
        name = "capture_alarm_0s_20260624-101500.jpg",
        kind = "incident",
        label = "alarm_0s",
        sizeBytes = 15,
    )
    private val photoHeaderLine =
        """{"photo": "capture_alarm_0s_20260624-101500.jpg", "size": 15, "encoding": "base64"}"""
    private val photoDoneLine = """{"done": 1}"""

    @Test
    fun `parses a PHOTOS listing into PhotoMeta, skipping banner and trailer`() {
        val lines = listOf(bannerLine, referenceRow, incidentRow, doneLine)

        val photos = PhotoParser.parseList(lines)

        assertEquals(2, photos.size)
        assertEquals("reference_frame_detected.jpg", photos[0].name)
        assertEquals("reference", photos[0].kind)
        assertNull(photos[0].label)
        assertEquals(84213, photos[0].sizeBytes)

        assertEquals("capture_alarm_0s_20260624-101500.jpg", photos[1].name)
        assertEquals("incident", photos[1].kind)
        assertEquals("alarm_0s", photos[1].label)
        assertEquals(142880, photos[1].sizeBytes)
    }

    @Test
    fun `empty PHOTOS listing parses to an empty list`() {
        val photos = PhotoParser.parseList(listOf(bannerLine, doneLine))

        assertTrue(photos.isEmpty())
    }

    @Test
    fun `parsePhoto decodes the base64 payload between the header and the trailer`() {
        val lines = listOf(photoHeaderLine, fakeJpegBase64, photoDoneLine)

        val bytes = PhotoParser.parsePhoto(photoMeta, lines)

        assertArrayEquals(fakeJpegBytes, bytes)
    }

    @Test
    fun `parsePhoto returns null when the reply has no payload line`() {
        val lines = listOf(photoHeaderLine) // truncated mid-stream, no payload, no trailer

        val bytes = PhotoParser.parsePhoto(photoMeta, lines)

        assertNull(bytes)
    }

    @Test
    fun `errorMessage extracts the message from an error reply`() {
        val lines = listOf("""{"error": "unknown photo 'foo.jpg'"}""")

        assertEquals("unknown photo 'foo.jpg'", PhotoParser.errorMessage(lines))
        assertNull(PhotoParser.parsePhoto(photoMeta, lines))
    }

    @Test
    fun `errorMessage is null for a successful PHOTO reply`() {
        val lines = listOf(photoHeaderLine, fakeJpegBase64, photoDoneLine)

        assertNull(PhotoParser.errorMessage(lines))
    }

    @Test
    fun `parseAll pairs each header with its base64 line across a multi-photo batch`() {
        // ALLPHOTOS headers (unlike a lone PHOTO reply's photoHeaderLine) always
        // carry "kind"/"label", since the client never sees a prior PHOTOS
        // listing to source them from.
        val firstHeaderLine =
            """{"photo": "capture_alarm_0s_20260624-101500.jpg", "size": 15, "encoding": "base64", "kind": "incident", "label": "alarm_0s"}"""
        val secondHeaderLine =
            """{"photo": "reference_frame_detected.jpg", "size": 15, "encoding": "base64", "kind": "reference", "label": null}"""
        val lines = listOf(
            bannerLine,
            firstHeaderLine,
            fakeJpegBase64,
            secondHeaderLine,
            fakeJpegBase64,
            """{"done": 2}""",
        )

        val photos = PhotoParser.parseAll(lines)

        assertEquals(2, photos.size)
        assertEquals("capture_alarm_0s_20260624-101500.jpg", photos[0].meta.name)
        assertEquals("alarm_0s", photos[0].meta.label)
        assertArrayEquals(fakeJpegBytes, photos[0].jpegBytes)

        assertEquals("reference_frame_detected.jpg", photos[1].meta.name)
        assertEquals("reference", photos[1].meta.kind)
        assertNull(photos[1].meta.label)
        assertArrayEquals(fakeJpegBytes, photos[1].jpegBytes)
    }

    @Test
    fun `parseAll on an empty batch (no photos available) returns an empty list`() {
        val photos = PhotoParser.parseAll(listOf(bannerLine, """{"done": 0}"""))

        assertTrue(photos.isEmpty())
    }
}
