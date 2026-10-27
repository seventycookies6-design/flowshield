package com.basaltfocus.core

import org.junit.Assert.*
import org.junit.Test

class MomentumTest {
    @Test fun completionAddsTenPointsForTwentyFiveMinutesWithoutResettingTheScore() {
        assertEquals(10.0, Momentum.afterCompletion(0.0, 25), 0.0)
        assertEquals(111.3, Momentum.afterCompletion(101.3, 25), 0.0)
        assertEquals(130.0, Momentum.afterCompletion(100.0, 75), 0.0)
    }

    @Test fun completionGainScalesByPlannedLength() {
        for ((minutes, score) in listOf(13 to 5.2, 20 to 8.0, 30 to 12.0,
            45 to 18.0, 60 to 24.0, 74 to 29.6)) {
            assertEquals("$minutes minutes", score, Momentum.afterCompletion(0.0, minutes), 0.0)
        }
    }

    @Test fun completionGainHasAFivePointMinimumAndThirtyPointMaximum() {
        for (minutes in listOf(Int.MIN_VALUE, -1, 0, 1, 12)) {
            assertEquals(25.0, Momentum.afterCompletion(20.0, minutes), 0.0)
        }
        for (minutes in listOf(75, 76, 200, Int.MAX_VALUE)) {
            assertEquals(50.0, Momentum.afterCompletion(20.0, minutes), 0.0)
        }
    }

    @Test fun completionRoundsTheWholeScoreToEvenAtOneDecimalPlace() {
        assertEquals(11.2, Momentum.afterCompletion(1.25, 25), 0.0)
        assertEquals(11.4, Momentum.afterCompletion(1.35, 25), 0.0)
        assertEquals(5.2, Momentum.afterCompletion(0.25, 1), 0.0)
        assertEquals(30.4, Momentum.afterCompletion(0.35, 500), 0.0)
    }

    @Test fun repeatedCompletionsAccumulateWithNoScoreCap() {
        var score = 0.0
        repeat(20) { score = Momentum.afterCompletion(score, 25) }
        assertEquals(200.0, score, 0.0)
    }
}
