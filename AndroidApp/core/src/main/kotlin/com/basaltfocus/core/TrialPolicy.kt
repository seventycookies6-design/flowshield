package com.basaltfocus.core

object TrialPolicy {
    private const val dayMillis = 86_400_000L
    private const val durationMillis = 7 * dayMillis

    /** Seven days, with at most one day of clock skew before the recorded start. */
    fun active(startMillis: Long?, nowMillis: Long): Boolean {
        val elapsed = elapsed(startMillis, nowMillis) ?: return false
        return elapsed >= -dayMillis && elapsed < durationMillis
    }

    fun daysLeft(startMillis: Long?, nowMillis: Long): Int {
        if (!active(startMillis, nowMillis)) return 0
        val remaining = durationMillis - (elapsed(startMillis, nowMillis) ?: return 0)
        return ((remaining + dayMillis - 1) / dayMillis).toInt().coerceIn(1, 7)
    }

    fun hasAccess(licensed: Boolean, startMillis: Long?, nowMillis: Long): Boolean =
        licensed || active(startMillis, nowMillis)

    fun earliest(a: Long?, b: Long?): Long? = when {
        a == null -> b
        b == null -> a
        else -> minOf(a, b)
    }

    private fun elapsed(startMillis: Long?, nowMillis: Long): Long? {
        if (startMillis == null) return null
        return try {
            Math.subtractExact(nowMillis, startMillis)
        } catch (_: ArithmeticException) {
            null
        }
    }
}
