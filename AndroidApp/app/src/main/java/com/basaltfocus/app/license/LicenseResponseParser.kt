package com.basaltfocus.app.license

import org.json.JSONException
import org.json.JSONObject
import org.json.JSONTokener

object LicenseResponseParser {
    /** A typed pair of verdict flags is required; absent fields never default to a rejection. */
    fun parse(httpStatus: Int, body: String): LicenseResult {
        if (httpStatus == 429) return rateLimited()
        if (httpStatus in 500..599 || httpStatus == 408 || httpStatus == 425) {
            return LicenseResult(message = "The license server is temporarily unavailable. Please try again.")
        }
        if (httpStatus !in 200..499 || httpStatus in 300..399) return unreadable()
        // Android's JSONTokener accepts comments, unquoted keys and trailing commas.
        // Those are malformed replies, not authoritative license verdicts.
        if (!JsonSyntax(body).isObject()) return unreadable()

        val json = try {
            val tokens = JSONTokener(body)
            val value = tokens.nextValue()
            if (value !is JSONObject || tokens.nextClean() != '\u0000') return unreadable()
            value
        } catch (_: JSONException) {
            return unreadable()
        }

        // optBoolean/optInt coerce strings. That would turn a broken response into a verdict.
        for (name in listOf("status", "reason", "error", "message", "email", "licenseKey")) {
            if (!json.isNull(name) && json.opt(name) !is String) return unreadable()
        }
        val reason = json.text("reason") ?: json.text("error")
        if (json.text("reason") == "rate_limited" || json.text("error") == "rate_limited") return rateLimited()
        val valid = json.opt("valid") as? Boolean ?: return unreadable()
        val isPro = json.opt("isPro") as? Boolean ?: return unreadable()
        val count = json.count("deviceCount") ?: return unreadable()
        val limit = json.count("deviceLimit") ?: return unreadable()

        if (isPro && (!valid || httpStatus !in 200..299 || reason != null)) return unreadable()

        val status = if (isPro) json.text("status") ?: "active"
            else reason ?: json.text("status") ?: "invalid"
        return LicenseResult(
            isPro = isPro,
            definitive = true,
            status = status,
            // Use controlled copy rather than server messages that can contain links or diagnostics.
            message = if (isPro) "License activated." else rejectionMessage(status),
            email = json.text("email"),
            licenseKey = json.text("licenseKey"),
            deviceCount = count,
            deviceLimit = limit
        )
    }

    internal fun rejectionMessage(reason: String): String = when (reason) {
        "missing_credentials" -> "Enter your license key or email address."
        "malformed_key" -> "That license key isn't in the FS-XXXX-XXXX-XXXX-XXXX format."
        "not_found" -> "We couldn't find a license for those details."
        "device_limit_reached" -> "This license is already active on the maximum number of devices. " +
            "Deactivate Basalt on a device you no longer use, then try again."
        else -> {
            val state = reason.removePrefix("license_").removePrefix("subscription_")
            when (state) {
                "refunded" -> "That license was refunded and is no longer active."
                "pending", "incomplete" -> "That license is not active yet."
                "canceled", "cancelled" -> "That license has been canceled."
                "past_due" -> "That license has an overdue payment."
                "unpaid" -> "That license has an unpaid balance."
                "expired", "incomplete_expired" -> "That license has expired."
                "paused" -> "That license is paused."
                "revoked" -> "That license has been revoked."
                else -> if ((reason.startsWith("license_") || reason.startsWith("subscription_")) &&
                    state.matches(Regex("[a-z]+(?:_[a-z]+)*"))) {
                    "That license is ${state.replace('_', ' ')}."
                } else "That license could not be validated."
            }
        }
    }

    private fun unreadable() =
        LicenseResult(message = "The license server returned an unreadable response. Please try again.")

    private fun rateLimited() = LicenseResult(status = "rate_limited",
        message = "Too many license requests. Please wait a minute and try again.")

    private fun JSONObject.text(name: String): String? =
        (opt(name) as? String)?.trim()?.takeIf { it.isNotEmpty() }

    /** Missing/null counts are optional; malformed counts make the response unreadable. */
    private fun JSONObject.count(name: String): Int? {
        if (isNull(name)) return 0
        val value = (opt(name) as? Number)?.toDouble() ?: return null
        return if (value.isFinite() && value >= 0 && value <= Int.MAX_VALUE && value % 1.0 == 0.0)
            value.toInt() else null
    }
}

/** Small syntax guard shared by Android's lenient JSON implementation and JVM org.json. */
private class JsonSyntax(private val text: String) {
    private var index = 0

    fun isObject(): Boolean {
        whitespace()
        if (peek() != '{' || !value(0)) return false
        whitespace()
        return index == text.length
    }

    private fun value(depth: Int): Boolean {
        if (depth > 64) return false
        whitespace()
        return when (peek()) {
            '{' -> {
                index++
                whitespace()
                if (take('}')) true else objectMembers(depth)
            }
            '[' -> {
                index++
                whitespace()
                if (take(']')) true else arrayValues(depth)
            }
            '"' -> string() != null
            't' -> literal("true")
            'f' -> literal("false")
            'n' -> literal("null")
            '-', in '0'..'9' -> number()
            else -> false
        }
    }

    private fun objectMembers(depth: Int): Boolean {
        val keys = mutableSetOf<String>()
        while (true) {
            whitespace()
            val key = string() ?: return false
            if (!keys.add(key)) return false
            whitespace()
            if (!take(':') || !value(depth + 1)) return false
            whitespace()
            if (take('}')) return true
            if (!take(',')) return false
        }
    }

    private fun arrayValues(depth: Int): Boolean {
        while (true) {
            if (!value(depth + 1)) return false
            whitespace()
            if (take(']')) return true
            if (!take(',')) return false
        }
    }

    private fun string(): String? {
        if (!take('"')) return null
        val decoded = StringBuilder()
        while (index < text.length) {
            when (val char = text[index++]) {
                '"' -> return decoded.toString()
                '\\' -> {
                    if (index == text.length) return null
                    val escaped = text[index++]
                    when (escaped) {
                        '"', '\\', '/' -> decoded.append(escaped)
                        'b' -> decoded.append('\b')
                        'f' -> decoded.append('\u000c')
                        'n' -> decoded.append('\n')
                        'r' -> decoded.append('\r')
                        't' -> decoded.append('\t')
                        'u' -> {
                            var code = 0
                            repeat(4) {
                                val hex = peek()
                                if (hex !in '0'..'9' && hex !in 'a'..'f' && hex !in 'A'..'F') return null
                                code = code * 16 + hex.digitToInt(16)
                                index++
                            }
                            decoded.append(code.toChar())
                        }
                        else -> return null
                    }
                }
                else -> if (char < ' ') return null else decoded.append(char)
            }
        }
        return null
    }

    private fun number(): Boolean {
        take('-')
        if (!take('0') && !digits()) return false
        if (take('.') && !digits()) return false
        if (take('e') || take('E')) {
            if (!take('+')) take('-')
            if (!digits()) return false
        }
        return true
    }

    private fun digits(): Boolean {
        val start = index
        while (peek() in '0'..'9') index++
        return index > start
    }

    private fun literal(value: String): Boolean {
        if (!text.startsWith(value, index)) return false
        index += value.length
        return true
    }

    private fun whitespace() {
        while (peek() == ' ' || peek() == '\t' || peek() == '\r' || peek() == '\n') index++
    }

    private fun take(char: Char): Boolean =
        if (peek() == char) { index++; true } else false

    private fun peek(): Char = text.getOrNull(index) ?: '\u0000'
}
