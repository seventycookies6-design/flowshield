package com.basaltfocus.app.license

import com.basaltfocus.core.LicenseKey
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject

/** Stateless POST /validate client. Persistence and platform device naming belong to the caller. */
class LicenseClient internal constructor(
    baseUrl: String,
    private val transport: LicenseTransport,
    private val pause: suspend (Long) -> Unit = { delay(it) },
    private val nowNanos: () -> Long = System::nanoTime
) {
    constructor(baseUrl: String) : this(baseUrl, OkHttpLicenseTransport(http))

    private val endpoint = baseUrl.trimEnd('/') + "/validate"

    /**
     * Progress runs in the caller's coroutine context. Cancellation cancels the HTTP call
     * and propagates to the caller, rather than becoming a negative license verdict.
     */
    suspend fun validate(
        input: String,
        deviceId: String,
        deviceName: String,
        onProgress: (String) -> Unit = {}
    ): LicenseResult {
        val trimmed = input.trim()
        if (trimmed.isEmpty()) return LicenseResult(message = "Enter your license key or email address.")

        val isEmail = '@' in trimmed
        val credential = if (isEmail) trimmed else LicenseKey.normalize(trimmed)
        if (!isEmail && !LicenseKey.isWellFormed(credential)) {
            return LicenseResult(definitive = true, status = "malformed_key",
                message = LicenseResponseParser.rejectionMessage("malformed_key"))
        }
        val payload = JSONObject().put(if (isEmail) "email" else "licenseKey", credential)
            .put("deviceId", deviceId).put("deviceName", deviceName).toString()
        val request = Request.Builder().url(endpoint)
            .post(payload.toRequestBody("application/json; charset=utf-8".toMediaType())).build()

        // The schedule is 72s; this also caps parsing, scheduling and transport overhead at 75s.
        return withTimeoutOrNull(75_000L) {
            coroutineScope {
                val start = nowNanos()
                onProgress(LicenseWaitCopy.ContactingMessage)
                val waking = launch(start = CoroutineStart.UNDISPATCHED) {
                    pause((LicenseWaitCopy.WakingUpAfterSeconds * 1_000).toLong())
                    onProgress(LicenseWaitCopy.WakingUpMessage)
                }
                try {
                    validateWithRetries(request, start, onProgress)
                } finally {
                    // Structured concurrency waits for this child to stop before validate returns.
                    waking.cancel()
                }
            }
        } ?: unreachable()
    }

    private suspend fun validateWithRetries(
        request: Request,
        start: Long,
        onProgress: (String) -> Unit
    ): LicenseResult {
        var last = unreachable()
        for (attempt in 1..LicenseWaitCopy.TotalAttempts) {
            if (attempt > 1) {
                pause((LicenseWaitCopy.RetryDelaysSeconds[attempt - 2] * 1_000).toLong())
                onProgress(LicenseWaitCopy.messageFor((nowNanos() - start) / 1_000_000_000.0))
            }
            try {
                val response = transport.post(request,
                    (LicenseWaitCopy.timeoutForAttempt(attempt) * 1_000).toLong())
                last = LicenseResponseParser.parse(response.status, response.body)
                // Throttling is not a verdict, and immediate retries would make it worse.
                if (last.definitive || last.status == "rate_limited") return last
                if (response.status !in 500..599 && response.status !in 200..299) return last
            } catch (_: IOException) {
                // Never include exception text, request bodies or identifiers in messages/logs.
                last = unreachable()
            }
        }
        return last
    }

    private fun unreachable() = LicenseResult(message =
        "Couldn't reach the license server. It may still be waking up. Please try again.")

    private companion object {
        // Whole-call timeouts below cover connection, TLS, request, and response body reads.
        // Disable hidden retries so the Windows schedule is the complete retry policy.
        val http = OkHttpClient.Builder()
            .connectTimeout(35, TimeUnit.SECONDS)
            .readTimeout(35, TimeUnit.SECONDS)
            .writeTimeout(35, TimeUnit.SECONDS)
            .retryOnConnectionFailure(false)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}

internal data class LicenseHttpResponse(val status: Int, val body: String)

internal fun interface LicenseTransport {
    suspend fun post(request: Request, timeoutMillis: Long): LicenseHttpResponse
}

/** The callback reads the body on OkHttp's dispatcher, never on the UI thread. */
internal class OkHttpLicenseTransport(private val callFactory: Call.Factory) : LicenseTransport {
    override suspend fun post(request: Request, timeoutMillis: Long): LicenseHttpResponse =
        suspendCancellableCoroutine { continuation ->
            val call = callFactory.newCall(request)
            call.timeout().timeout(timeoutMillis, TimeUnit.MILLISECONDS)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    continuation.resumeWithException(e)
                }

                override fun onResponse(call: Call, response: Response) {
                    try {
                        val result = response.use { LicenseHttpResponse(it.code, it.body.string()) }
                        continuation.resume(result)
                    } catch (failure: IOException) {
                        continuation.resumeWithException(failure)
                    }
                }
            })
        }
}
