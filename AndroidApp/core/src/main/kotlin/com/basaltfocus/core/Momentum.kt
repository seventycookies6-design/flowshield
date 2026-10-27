package com.basaltfocus.core

import kotlin.math.abs
import kotlin.math.round

object Momentum {
    fun afterCompletion(score: Double, plannedMinutes: Int): Double =
        roundMomentum(score + 10 * (plannedMinutes / 25.0).coerceIn(0.5, 3.0))

    /** Windows shows momentum as a whole number (ToString("0"), which rounds midpoints away from zero). */
    fun display(score: Double): String = java.math.BigDecimal.valueOf(score)
        .setScale(0, java.math.RoundingMode.HALF_UP).toPlainString()

    /** The summary line, as Windows' SummaryMomentumText: "+10 → 20". */
    fun change(before: Double, after: Double): String {
        val delta = java.math.BigDecimal.valueOf(after - before).setScale(0, java.math.RoundingMode.HALF_EVEN).toInt()
        val sign = if (delta > 0) "+$delta" else "$delta"
        return "$sign → ${display(after)}"
    }

    /** Windows' MomentumTrend.Explanation, word for word. */
    val explanation = listOf(
        "Finishing a sprint adds 10 points for a 25-minute one, scaled by how long it was: 5 points at the least, 30 at the most.",
        "Ending a sprint early takes a share of what you have, plus a little: about 15% and 2 points at Soft or Firm, 30% and 5 at Sealed. It never goes below zero.",
        "Nothing happens while you are away. Momentum does not decay overnight and it never resets, so a quiet week costs you nothing and a bad day is not the end of anything.",
    )
}

/** .NET Math.Round(value, 1): round midpoints to even, retaining large values unchanged. */
internal fun roundMomentum(value: Double): Double =
    if (abs(value) >= 1e16) value else round(value * 10) / 10
