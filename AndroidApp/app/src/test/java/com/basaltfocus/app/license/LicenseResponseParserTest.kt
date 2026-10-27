package com.basaltfocus.app.license

import org.junit.Assert.*
import org.junit.Test

class LicenseResponseParserTest {
    @Test
    fun activeLicenseIncludesIdentityAndSeatCounts() {
        val result = LicenseResponseParser.parse(200, """
            {"valid":true,"isPro":true,"status":"active","email":"test@example.invalid",
             "licenseKey":"FS-TEST-TEST-TEST-TEST","deviceCount":2,"deviceLimit":3}
        """.trimIndent())

        assertTrue(result.definitive)
        assertTrue(result.isPro)
        assertEquals("active", result.status)
        assertEquals("test@example.invalid", result.email)
        assertEquals("FS-TEST-TEST-TEST-TEST", result.licenseKey)
        assertEquals(2, result.deviceCount)
        assertEquals(3, result.deviceLimit)
    }

    @Test
    fun emailValidationCanOmitKeyAndEmail() {
        val result = LicenseResponseParser.parse(200, """{"valid":true,"isPro":true,"status":"active"}""")

        assertTrue(result.definitive)
        assertTrue(result.isPro)
        assertNull(result.licenseKey)
        assertNull(result.email)
        assertEquals(0, result.deviceCount)
        assertEquals(0, result.deviceLimit)
    }

    @Test
    fun positiveVerdictMayOmitOptionalStatus() {
        val result = LicenseResponseParser.parse(200, """{"valid":true,"isPro":true}""")
        assertTrue(result.isPro)
        assertEquals("active", result.status)
    }

    @Test
    fun everyKnownRejectionHasLicenseCopy() {
        val cases = mapOf(
            "missing_credentials" to "Enter your license key or email address.",
            "malformed_key" to "That license key isn't in the FS-XXXX-XXXX-XXXX-XXXX format.",
            "not_found" to "We couldn't find a license for those details.",
            "device_limit_reached" to "This license is already active on the maximum number of devices. Deactivate Basalt on a device you no longer use, then try again.",
            "license_refunded" to "That license was refunded and is no longer active.",
            "license_pending" to "That license is not active yet.",
            "license_canceled" to "That license has been canceled.",
            "license_cancelled" to "That license has been canceled.",
            "subscription_canceled" to "That license has been canceled.",
            "subscription_past_due" to "That license has an overdue payment.",
            "subscription_unpaid" to "That license has an unpaid balance.",
            "subscription_incomplete" to "That license is not active yet.",
            "subscription_incomplete_expired" to "That license has expired.",
            "subscription_paused" to "That license is paused.",
            "license_expired" to "That license has expired.",
            "license_revoked" to "That license has been revoked.",
            "license_future_status" to "That license is future status.",
            "subscription_future_status" to "That license is future status.",
            "unrecognized" to "That license could not be validated."
        )

        for ((reason, message) in cases) {
            val result = LicenseResponseParser.parse(200,
                """{"valid":false,"isPro":false,"reason":"$reason"}""")
            assertTrue(reason, result.definitive)
            assertFalse(reason, result.isPro)
            assertEquals(reason, reason, result.status)
            assertEquals(reason, message, result.message)
        }
    }

    @Test
    fun seatRejectionTakesPrecedenceOverActiveStatusAndKeepsCounts() {
        val result = LicenseResponseParser.parse(200, """
            {"valid":false,"isPro":false,"status":"active","reason":"device_limit_reached",
             "deviceCount":3,"deviceLimit":3,"message":"Buy at https://example.invalid"}
        """.trimIndent())
        assertEquals("device_limit_reached", result.status)
        assertTrue(result.definitive)
        assertFalse(result.isPro)
        assertEquals(3, result.deviceCount)
        assertEquals(3, result.deviceLimit)
        assertFalse(result.message.contains("http"))
        assertFalse(result.message.contains("Buy"))
    }

    @Test
    fun errorFieldAndHttp400MissingCredentialsAreAuthoritative() {
        val result = LicenseResponseParser.parse(400, """
            {"valid":false,"isPro":false,"error":"missing_credentials"}
        """.trimIndent())
        assertTrue(result.definitive)
        assertEquals("missing_credentials", result.status)
    }

    @Test
    fun explicitNegativeVerdictNeedsNoRecognizedStatus() {
        for (body in listOf(
            """{"valid":false,"isPro":false}""",
            """{"valid":true,"isPro":false,"status":"future_status"}"""
        )) {
            val result = LicenseResponseParser.parse(200, body)
            assertTrue(body, result.definitive)
            assertFalse(body, result.isPro)
        }
    }

    @Test
    fun statusAloneNeverGrantsOrRevokesAccess() {
        for (body in listOf(
            "{}", "null", "[]", "", "not JSON", "{", "{\"valid\":false,",
            """{"status":"active"}""", """{"reason":"not_found"}""",
            """{"valid":false}""", """{"isPro":false}""",
            """{"valid":true,"isPro":"true"}""",
            """{"valid":"false","isPro":false,"reason":"not_found"}""",
            """{"valid":false,"isPro":0}""",
            """{"valid":null,"isPro":false}""",
            """{"valid":false,"isPro":null}""",
            """{"valid":false,"isPro":true}""",
            """{"valid":true,"isPro":true,"reason":"license_refunded"}""",
            """{"valid":false,"isPro":false,"reason":7}""",
            """{"valid":true,"isPro":true,"status":false}""",
            """{"valid":true,"isPro":true,"email":7}""",
            """{"valid":true,"isPro":true,"licenseKey":false}""",
            """{"valid":false,"isPro":false,"message":[]}""",
            """{"valid":true,"isPro":true,"deviceLimit":"3"}""",
            """{"valid":true,"isPro":true} trailing""",
            """{'valid':true,'isPro':true}""",
            """{valid:true,isPro:true}""",
            """{"valid":true,"isPro":true,}""",
            """{"valid":true,"isPro":true,"ignored":[1,,2]}""",
            """{"valid":true,"isPro":true,"ignored":01}""",
            """{"valid":true,"isPro":true /* comment */}""",
            """{"valid":true,"isPro":true,"isPro":false}""",
            """{"valid":true,"isPro":true,"is\u0050ro":false}""",
            """{"valid":true,"isPro":true,"ignored":"\uZZZZ"}""",
            """{"valid":true,"isPro":true,"ignored":"\x20"}"""
        )) {
            val result = LicenseResponseParser.parse(200, body)
            assertFalse(body, result.definitive)
            assertFalse(body, result.isPro)
        }
    }

    @Test
    fun validExtraFieldsAndJsonEscapesAreAllowed() {
        val result = LicenseResponseParser.parse(200, """
            {"valid":true,"isPro":true,"email":"a\u0040example.invalid",
             "ignored":{"array":[true,false,null,-12.5e+2,"quote\"slash\\"]}}
        """.trimIndent())
        assertTrue(result.isPro)
        assertEquals("a@example.invalid", result.email)
    }

    @Test
    fun excessiveNestingIsUnreadableInsteadOfOverflowingTheStack() {
        val body = """{"valid":true,"isPro":true,"ignored":""" + "[".repeat(100) + "0" +
            "]".repeat(100) + "}"
        assertFalse(LicenseResponseParser.parse(200, body).definitive)
    }

    @Test
    fun countsAreNotCoercedFromStringsFractionsOrNegativeNumbers() {
        for (count in listOf("\"3\"", "1.5", "-1", "2147483648", "true")) {
            val result = LicenseResponseParser.parse(200,
                """{"valid":true,"isPro":true,"deviceCount":$count}""")
            assertFalse(count, result.definitive)
        }
    }

    @Test
    fun nullOptionalFieldsAreAllowed() {
        val result = LicenseResponseParser.parse(200, """
            {"valid":true,"isPro":true,"email":null,"licenseKey":null,
             "status":null,"deviceCount":null,"deviceLimit":null}
        """.trimIndent())
        assertTrue(result.isPro)
        assertNull(result.email)
    }

    @Test
    fun rateLimitPreservesCachedAccessEvenWithARejectionBody() {
        for (body in listOf("", """{"error":"rate_limited"}""",
            """{"valid":false,"isPro":false,"reason":"not_found"}""")) {
            val result = LicenseResponseParser.parse(429, body)
            assertFalse(result.definitive)
            assertEquals("rate_limited", result.status)
            assertTrue(LicenseCachePolicy.keepAccess(true, result))
        }
    }

    @Test
    fun bodyRateLimitIsNotALicenseVerdict() {
        val result = LicenseResponseParser.parse(200, """
            {"valid":false,"isPro":false,"error":"rate_limited"}
        """.trimIndent())
        assertFalse(result.definitive)
    }

    @Test
    fun serverErrorsAndUnexpectedHttpResponsesNeverBecomeVerdicts() {
        for (code in listOf(0, 302, 404, 408, 425, 500, 502, 503, 599)) {
            val result = LicenseResponseParser.parse(code,
                """{"valid":true,"isPro":true,"status":"active"}""")
            assertFalse(code.toString(), result.definitive)
            assertFalse(code.toString(), result.isPro)
        }
        assertFalse(LicenseResponseParser.parse(503,
            """{"valid":false,"isPro":false,"reason":"not_found"}""").definitive)
        assertFalse(LicenseResponseParser.parse(404, """{"error":"not_found"}""").definitive)
    }
}
