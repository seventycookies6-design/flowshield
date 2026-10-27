package com.basaltfocus.core

import kotlin.math.abs
import kotlin.math.round

object Momentum {
    fun afterCompletion(score: Double, plannedMinutes: Int): Double =
        roundMomentum(score + 10 * (plannedMinutes / 25.0).coerceIn(0.5, 3.0))
}

/** .NET Math.Round(value, 1): round midpoints to even, retaining large values unchanged. */
internal fun roundMomentum(value: Double): Double =
    if (abs(value) >= 1e16) value else round(value * 10) / 10
