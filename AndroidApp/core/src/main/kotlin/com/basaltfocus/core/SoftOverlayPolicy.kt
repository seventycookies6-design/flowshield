package com.basaltfocus.core

import java.util.Locale

/** Per-sprint notice state. Callers serialize foreground events and reset at sprint boundaries. */
class SoftOverlayPolicy {
    var tries: Int = 0
        private set
    var turnedBack: Int = 0
        private set

    private val quietUntil = mutableMapOf<String, Long>()
    private var sighting: String? = null
    private var showing = false

    fun shouldShow(packageName: String, nowMillis: Long): Boolean {
        val key = packageName.lowercase(Locale.ROOT)
        val isNewSighting = sighting != key
        sighting = key
        if (!isNewSighting || isQuiet(key, nowMillis)) return false
        showing = true
        tries++
        return true
    }

    /** Clear only the foreground sighting; allowances and counters belong to the entire sprint. */
    fun leftForeground(): Boolean {
        sighting = null
        val wasShowing = showing
        showing = false
        return wasShowing
    }

    fun allowFiveMinutes(packageName: String, nowMillis: Long) {
        quieten(packageName, nowMillis, allowWindowMillis)
    }

    fun backToWork(packageName: String, nowMillis: Long) {
        turnedBack++
        quieten(packageName, nowMillis, backToWorkQuietMillis)
    }

    fun isQuiet(packageName: String, nowMillis: Long): Boolean =
        quietUntil[packageName.lowercase(Locale.ROOT)]?.let { nowMillis < it } ?: false

    fun reset() {
        quietUntil.clear()
        sighting = null
        showing = false
        tries = 0
        turnedBack = 0
    }

    private fun quieten(packageName: String, nowMillis: Long, windowMillis: Long) {
        val until = if (nowMillis > Long.MAX_VALUE - windowMillis) Long.MAX_VALUE else nowMillis + windowMillis
        quietUntil[packageName.lowercase(Locale.ROOT)] = until
        sighting = null
        showing = false
    }

    companion object {
        const val allowWindowMillis = 300_000L
        const val backToWorkQuietMillis = 5_000L
        fun allowWaitMillis(tryNumber: Int): Long = when {
            tryNumber <= 1 -> 5_000L
            tryNumber == 2 -> 10_000L
            tryNumber == 3 -> 20_000L
            else -> 30_000L
        }
    }
}
