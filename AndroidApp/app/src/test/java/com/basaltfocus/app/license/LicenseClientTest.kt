package com.basaltfocus.app.license

import java.io.IOException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.yield
import okhttp3.Request
import okio.Buffer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LicenseClientTest {
    private val key = "FS-0123-4567-89AB-CDEQ"

    @Test
    fun keyRequestContainsExactlyTheKeyAndDeviceFields() = runBlocking {
        var sent: Request? = null
        val client = client(LicenseTransport { request, timeout ->
            sent = request
            assertEquals(35_000L, timeout)
            activeResponse()
        })
        val result = client.validate("  fs-0123-4567-89ab-cdeq  ", "hashed-device", "Example Phone")

        assertTrue(result.isPro)
        val request = checkNotNull(sent)
        assertEquals("https://example.invalid/license/validate", request.url.toString())
        assertEquals("POST", request.method)
        val json = requestJson(request)
        assertEquals(setOf("licenseKey", "deviceId", "deviceName"), json.keys().asSequence().toSet())
        assertEquals(key, json.getString("licenseKey"))
        assertEquals("hashed-device", json.getString("deviceId"))
        assertEquals("Example Phone", json.getString("deviceName"))
        assertEquals("application/json; charset=utf-8", request.body!!.contentType().toString())
    }

    @Test
    fun emailRequestDoesNotIncludeAKeyOrInventResponseIdentity() = runBlocking {
        var sent: Request? = null
        val result = client(LicenseTransport { request, _ ->
            sent = request
            activeResponse()
        }).validate("  person@example.invalid  ", "hashed-device", "Example Phone")

        val json = requestJson(checkNotNull(sent))
        assertEquals(setOf("email", "deviceId", "deviceName"), json.keys().asSequence().toSet())
        assertEquals("person@example.invalid", json.getString("email"))
        assertTrue(result.definitive)
        assertNull(result.licenseKey)
        assertNull(result.email)
    }

    @Test
    fun malformedKeyIsRejectedLocallyUsingTheCorePolicy() = runBlocking {
        var attempts = 0
        val result = client(LicenseTransport { _, _ ->
            attempts++
            LicenseHttpResponse(200, """{"valid":false,"isPro":false,"reason":"malformed_key"}""")
        }).validate("not-a-key", "hash", "Phone")
        assertEquals(0, attempts)
        assertTrue(result.definitive)
        assertEquals("malformed_key", result.status)
    }

    @Test
    fun blankEntryDoesNotMakeANetworkRequestOrRevokeCachedAccess() = runBlocking {
        val result = client(LicenseTransport { _, _ -> error("No request expected") })
            .validate(" \t\n", "hash", "Phone")
        assertFalse(result.definitive)
        assertTrue(LicenseCachePolicy.keepAccess(true, result))
        assertEquals("Enter your license key or email address.", result.message)
    }

    @Test
    fun offlineUsesExactlyTheWindowsTimeoutsAndBackoffsAndPreservesCache() = runBlocking {
        val timeouts = mutableListOf<Long>()
        val backoffs = mutableListOf<Long>()
        val messages = mutableListOf<String>()
        val result = client(LicenseTransport { _, timeout ->
            timeouts += timeout
            throw IOException("Sensitive server details must not reach messages")
        }, backoffs).validate(key, "hash", "Phone", messages::add)

        assertEquals(listOf(35_000L, 15_000L, 15_000L), timeouts)
        assertEquals(listOf(2_000L, 5_000L), backoffs)
        assertFalse(result.definitive)
        assertTrue(LicenseCachePolicy.keepAccess(true, result))
        assertFalse(LicenseCachePolicy.keepAccess(false, result))
        assertFalse(result.message.contains("Sensitive"))
        assertTrue(messages.isNotEmpty())
    }

    @Test
    fun serverErrorsRetryUntilARealAnswerArrives() = runBlocking {
        var attempts = 0
        val backoffs = mutableListOf<Long>()
        val result = client(LicenseTransport { _, _ ->
            attempts++
            if (attempts < 3) LicenseHttpResponse(503, """{"valid":false,"isPro":false}""")
            else activeResponse()
        }, backoffs).validate(key, "hash", "Phone")
        assertEquals(3, attempts)
        assertEquals(listOf(2_000L, 5_000L), backoffs)
        assertTrue(result.isPro)
    }

    @Test
    fun unreadableSuccessResponsesRetryWithoutRevokingAccess() = runBlocking {
        var attempts = 0
        val result = client(LicenseTransport { _, _ ->
            attempts++
            LicenseHttpResponse(200, "<html>temporarily unavailable</html>")
        }).validate(key, "hash", "Phone")
        assertEquals(3, attempts)
        assertFalse(result.definitive)
        assertTrue(LicenseCachePolicy.keepAccess(true, result))
    }

    @Test
    fun authoritativeRejectionsAndRateLimitsAreNotRetried() = runBlocking {
        for (response in listOf(
            LicenseHttpResponse(200, """{"valid":false,"isPro":false,"reason":"not_found"}"""),
            LicenseHttpResponse(400, """{"valid":false,"isPro":false,"error":"missing_credentials"}"""),
            LicenseHttpResponse(429, """{"error":"rate_limited"}""")
        )) {
            var attempts = 0
            val backoffs = mutableListOf<Long>()
            val result = client(LicenseTransport { _, _ -> attempts++; response }, backoffs)
                .validate(key, "hash", "Phone")
            assertEquals(1, attempts)
            assertTrue(backoffs.isEmpty())
            assertEquals(response.status != 429, result.definitive)
        }
    }

    @Test
    fun wakeMessageArrivesWhileTheFirstRequestIsStillPending() = runBlocking {
        val wake = CompletableDeferred<Unit>()
        val response = CompletableDeferred<LicenseHttpResponse>()
        val messages = mutableListOf<String>()
        val client = LicenseClient("https://example.invalid",
            LicenseTransport { _, _ -> response.await() },
            pause = { milliseconds ->
                assertEquals(8_000L, milliseconds)
                wake.await()
            })
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            client.validate(key, "hash", "Phone", messages::add)
        }
        assertEquals(listOf(LicenseWaitCopy.ContactingMessage), messages)
        wake.complete(Unit)
        yield()
        assertFalse(pending.isCompleted)
        assertEquals(listOf(LicenseWaitCopy.ContactingMessage, LicenseWaitCopy.WakingUpMessage), messages)
        response.complete(activeResponse())
        assertTrue(pending.await().isPro)
    }

    @Test
    fun fastResponseStopsTheWakeReporter() = runBlocking {
        val stopped = CompletableDeferred<Unit>()
        val messages = mutableListOf<String>()
        val client = LicenseClient("https://example.invalid", LicenseTransport { _, _ -> activeResponse() },
            pause = { try { awaitCancellation() } finally { stopped.complete(Unit) } })
        client.validate(key, "hash", "Phone", messages::add)
        assertTrue(stopped.isCompleted)
        assertEquals(listOf(LicenseWaitCopy.ContactingMessage), messages)
    }

    @Test
    fun callerCancellationPropagatesAndStopsRetriesAndProgress() = runBlocking {
        var attempts = 0
        val messages = mutableListOf<String>()
        val client = client(LicenseTransport { _, _ -> attempts++; awaitCancellation() })
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            client.validate(key, "hash", "Phone", messages::add)
        }
        pending.cancelAndJoin()
        assertTrue(pending.isCancelled)
        assertEquals(1, attempts)
        assertEquals(listOf(LicenseWaitCopy.ContactingMessage), messages)
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test
    fun entireOperationIsCappedAtSeventyFiveSeconds() = runTest {
        val client = LicenseClient("https://example.invalid", LicenseTransport { _, _ -> awaitCancellation() })
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            client.validate(key, "hash", "Phone")
        }
        advanceTimeBy(74_999L)
        runCurrent()
        assertFalse(pending.isCompleted)
        advanceTimeBy(1L)
        runCurrent()
        val result = pending.await()
        assertFalse(result.definitive)
        assertTrue(LicenseCachePolicy.keepAccess(true, result))
    }

    private fun client(transport: LicenseTransport, backoffs: MutableList<Long> = mutableListOf()) =
        LicenseClient("https://example.invalid/license/", transport,
            pause = { milliseconds ->
                if (milliseconds == 8_000L) awaitCancellation() else backoffs.add(milliseconds)
            }, nowNanos = { 0L })

    private fun activeResponse() =
        LicenseHttpResponse(200, """{"valid":true,"isPro":true,"status":"active"}""")

    private fun requestJson(request: Request): JSONObject {
        val buffer = Buffer()
        request.body!!.writeTo(buffer)
        return JSONObject(buffer.readUtf8())
    }
}
