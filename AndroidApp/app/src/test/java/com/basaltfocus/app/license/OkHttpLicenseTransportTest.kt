package com.basaltfocus.app.license

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.reflect.KClass
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import okhttp3.Call
import okhttp3.Callback
import okhttp3.EventListener
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import okio.ForwardingSource
import okio.Timeout
import okio.buffer
import org.junit.Assert.*
import org.junit.Test

class OkHttpLicenseTransportTest {
    @Test
    fun requestIsEnqueuedAndUsesItsWholeCallTimeout() = runBlocking {
        val factory = TrackingFactory()
        val transport = OkHttpLicenseTransport(factory)
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            transport.post(request, 35_000L)
        }
        val call = checkNotNull(factory.call)
        assertTrue(call.isExecuted())
        assertEquals(TimeUnit.SECONDS.toNanos(35), call.timeout().timeoutNanos())
        call.respond(200, "response body")
        assertEquals(LicenseHttpResponse(200, "response body"), pending.await())
    }

    @Test
    fun retryUsesFifteenSeconds() = runBlocking {
        val factory = TrackingFactory()
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            OkHttpLicenseTransport(factory).post(request, 15_000L)
        }
        val call = checkNotNull(factory.call)
        assertEquals(TimeUnit.SECONDS.toNanos(15), call.timeout().timeoutNanos())
        call.respond(503, "unavailable")
        assertEquals(503, pending.await().status)
    }

    @Test
    fun coroutineCancellationCancelsTheUnderlyingCall() = runBlocking {
        val factory = TrackingFactory()
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            OkHttpLicenseTransport(factory).post(request, 35_000L)
        }
        pending.cancelAndJoin()
        assertTrue(checkNotNull(factory.call).isCanceled())
    }

    @Test
    fun networkFailureIsReportedWithoutBlockingExecute() = runBlocking {
        val factory = TrackingFactory()
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            try {
                OkHttpLicenseTransport(factory).post(request, 35_000L)
                null
            } catch (failure: IOException) {
                failure
            }
        }
        val cause = IllegalStateException("connection unavailable")
        val failure = IOException("offline", cause)
        val call = checkNotNull(factory.call)
        call.callback!!.onFailure(call, failure)
        val reported = pending.await()
        // Coroutine stacktrace recovery may copy the exception; identity is not the contract.
        assertNotNull(reported)
        assertEquals(IOException::class.java, reported!!.javaClass)
        assertEquals("offline", reported.message)
        val rootCause = generateSequence<Throwable>(reported) { it.cause }.last()
        assertEquals(IllegalStateException::class.java, rootCause.javaClass)
        assertEquals("connection unavailable", rootCause.message)
    }

    @Test
    fun responseArrivingAfterCancellationIsStillClosed() = runBlocking {
        val factory = TrackingFactory()
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            OkHttpLicenseTransport(factory).post(request, 35_000L)
        }
        pending.cancelAndJoin()
        val body = TrackedBody()
        checkNotNull(factory.call).respond(200, body)
        assertTrue(body.closed)
        assertTrue(pending.isCancelled)
    }

    @Test
    fun bodyReadFailureClosesTheResponseAndPropagatesAsTransportFailure() = runBlocking {
        val factory = TrackingFactory()
        val pending = async(start = CoroutineStart.UNDISPATCHED) {
            try {
                OkHttpLicenseTransport(factory).post(request, 35_000L)
                false
            } catch (_: IOException) {
                true
            }
        }
        val body = TrackedBody(failRead = true)
        checkNotNull(factory.call).respond(200, body)
        assertTrue(pending.await())
        assertTrue(body.closed)
    }

    private val request = Request.Builder().url("https://example.invalid/validate").build()

    private class TrackingFactory : Call.Factory {
        var call: TrackingCall? = null
        override fun newCall(request: Request): Call = TrackingCall(request).also { call = it }
    }

    private class TrackingCall(private val value: Request) : Call {
        var callback: Callback? = null
        private var canceled = false
        private val callTimeout = Timeout()
        override fun request() = value
        override fun execute(): Response = error("Blocking execute must never be used")
        override fun enqueue(responseCallback: Callback) { callback = responseCallback }
        override fun cancel() { canceled = true }
        override fun isExecuted() = callback != null
        override fun isCanceled() = canceled
        override fun timeout() = callTimeout
        override fun addEventListener(eventListener: EventListener) = Unit
        override fun <T : Any> tag(type: KClass<T>): T? = null
        override fun <T> tag(type: Class<out T>): T? = null
        override fun <T : Any> tag(type: KClass<T>, computeIfAbsent: () -> T): T = computeIfAbsent()
        override fun <T : Any> tag(type: Class<T>, computeIfAbsent: () -> T): T = computeIfAbsent()
        public override fun clone(): Call = TrackingCall(value)

        fun respond(status: Int, body: String) {
            respond(status, body.toResponseBody())
        }

        fun respond(status: Int, body: ResponseBody) {
            callback!!.onResponse(this, Response.Builder().request(value)
                .protocol(Protocol.HTTP_1_1).code(status).message("Test response")
                .body(body).build())
        }
    }

    private class TrackedBody(failRead: Boolean = false) : ResponseBody() {
        var closed = false
        private val data = object : ForwardingSource(Buffer().writeUtf8("body")) {
            override fun read(sink: Buffer, byteCount: Long): Long {
                if (failRead) throw IOException("Connection dropped while reading")
                return super.read(sink, byteCount)
            }

            override fun close() {
                closed = true
                super.close()
            }
        }.buffer()
        override fun contentType() = null
        override fun contentLength() = -1L
        override fun source() = data
    }
}
