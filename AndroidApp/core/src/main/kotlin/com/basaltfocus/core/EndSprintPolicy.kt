package com.basaltfocus.core

import kotlin.math.max

enum class Shield { SOFT, FIRM, SEALED }

enum class EndFlow { CANCEL, IMMEDIATE, CONFIRM, SEALED }

object EndSprintPolicy {
    const val graceMillis = 120_000L
    const val phrase = "end my sprint"
    private val phraseWhitespace = Regex("[\\u0009-\\u000d\\u0085\\p{Z}]+")

    /** The grace period is exclusive: at exactly two minutes the shield's end flow applies. */
    fun flowFor(shield: Shield, elapsedMillis: Long): EndFlow =
        if (elapsedMillis < graceMillis) EndFlow.CANCEL else when (shield) {
            Shield.SOFT -> EndFlow.IMMEDIATE
            Shield.FIRM -> EndFlow.CONFIRM
            Shield.SEALED -> EndFlow.SEALED
        }

    fun delayMillis(flow: EndFlow): Long = when (flow) {
        EndFlow.CONFIRM -> 5_000L
        EndFlow.SEALED -> 30_000L
        EndFlow.CANCEL, EndFlow.IMMEDIATE -> 0L
    }

    /** Match Windows' whitespace splitting, including nonbreaking spaces and NEL. */
    fun phraseMatches(typed: String?): Boolean = phraseWhitespace.split(typed.orEmpty())
        .filter { it.isNotEmpty() }
        .joinToString(" ")
        .equals(phrase, ignoreCase = true)

    fun momentumAfterEndingEarly(score: Double, shield: Shield): Double = roundMomentum(
        max(0.0, if (shield == Shield.SEALED) score * 0.7 - 5 else score * 0.85 - 2),
    )
}
