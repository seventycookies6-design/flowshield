package com.basaltfocus.core

import kotlin.math.max

/**
 * What the notice over a blocked app says. Ported from Windows' SoftOverlayCopy, with the
 * "Close" wording removed: Android Basalt never closes an app, it only shows this notice and,
 * at Firm and Sealed, returns to the home screen.
 */
object SoftNoticeCopy {
    /** Four calm ways to say the same thing, chosen by try number so the notice doesn't go stale. */
    fun sentence(label: String, until: String, tryNumber: Int): String = when ((max(tryNumber, 1) - 1) % 4) {
        0 -> "$label is on your blocklist until $until"
        1 -> "You set this time aside until $until"
        2 -> "$label can wait until $until"
        else -> "$label will still be there after $until"
    }

    /** "3rd try this sprint". */
    fun tryLine(tryNumber: Int): String {
        val n = max(tryNumber, 1)
        val suffix = if (n % 100 in 11..13) "th" else when (n % 10) {
            1 -> "st"
            2 -> "nd"
            3 -> "rd"
            else -> "th"
        }
        return "$n$suffix try this sprint"
    }

    /** The Allow button: its countdown after a middle dot while the wait runs, the plain label after. */
    fun allowLabel(leftMillis: Long): String {
        if (leftMillis <= 0) return "Allow 5 minutes"
        val seconds = ((leftMillis + 999) / 1000).toInt()
        return "Allow 5 minutes · %d:%02d".format(seconds / 60, seconds % 60)
    }

    /** "25 minutes left in this sprint". */
    fun timeLeft(remainingMillis: Long): String {
        if (remainingMillis <= 0) return "This sprint is ending"
        val minutes = ((remainingMillis + 59_999) / 60_000).toInt()
        return if (minutes == 1) "1 minute left in this sprint" else "$minutes minutes left in this sprint"
    }

    /** Soft's promise under its buttons, in words that are true on Android. */
    const val softNote = "Basalt doesn't close apps. You choose what happens next."

    /** Firm and Sealed: the countdown before Basalt goes to the home screen. */
    fun homeLine(secondsLeft: Int): String = if (secondsLeft <= 0) "Going to your home screen. This app stays open in the background."
        else "Going to your home screen in $secondsLeft s. This app stays open in the background."

    const val firmSeconds = 3
}
