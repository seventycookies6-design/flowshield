package com.basaltfocus.core

import java.util.Locale
import org.junit.Assert.*
import org.junit.Test

class SprintLengthTest {
    @Test fun presetsMatchWindowsToday() {
        assertEquals(listOf(15, 25, 45, 60, 90), SprintLength.presets)
    }

    @Test fun customRangeIsFiveToTwoHundredFortyLikeWindows() {
        assertFalse(SprintLength.isValid(4))
        assertTrue(SprintLength.isValid(5))
        assertTrue(SprintLength.isValid(240))
        assertFalse(SprintLength.isValid(241))
        assertFalse(SprintLength.isValid(null))
        assertEquals("Choose between 5 and 240 minutes.", SprintLength.error(1))
        assertNull(SprintLength.error(25))
    }

    @Test fun onlyDebugBuildsAllowOneMinuteSprints() {
        assertFalse(SprintLength.isValid(1, allowShort = false))
        assertTrue(SprintLength.isValid(1, allowShort = true))
        assertFalse(SprintLength.isValid(0, allowShort = true))
        assertFalse(SprintLength.isValid(241, allowShort = true))
    }
}

class SoftNoticeCopyTest {
    @Test fun sentenceCyclesThroughFourWordingsByTry() {
        assertEquals("Chrome is on your blocklist until 5:45 PM", SoftNoticeCopy.sentence("Chrome", "5:45 PM", 1))
        assertEquals("You set this time aside until 5:45 PM", SoftNoticeCopy.sentence("Chrome", "5:45 PM", 2))
        assertEquals("Chrome can wait until 5:45 PM", SoftNoticeCopy.sentence("Chrome", "5:45 PM", 3))
        assertEquals("Chrome will still be there after 5:45 PM", SoftNoticeCopy.sentence("Chrome", "5:45 PM", 4))
        assertEquals(SoftNoticeCopy.sentence("Chrome", "x", 1), SoftNoticeCopy.sentence("Chrome", "x", 5))
        assertEquals(SoftNoticeCopy.sentence("Chrome", "x", 1), SoftNoticeCopy.sentence("Chrome", "x", 0))
    }

    @Test fun tryLineUsesEnglishOrdinals() {
        assertEquals("1st try this sprint", SoftNoticeCopy.tryLine(1))
        assertEquals("2nd try this sprint", SoftNoticeCopy.tryLine(2))
        assertEquals("3rd try this sprint", SoftNoticeCopy.tryLine(3))
        assertEquals("4th try this sprint", SoftNoticeCopy.tryLine(4))
        assertEquals("11th try this sprint", SoftNoticeCopy.tryLine(11))
        assertEquals("12th try this sprint", SoftNoticeCopy.tryLine(12))
        assertEquals("21st try this sprint", SoftNoticeCopy.tryLine(21))
        assertEquals("1st try this sprint", SoftNoticeCopy.tryLine(0))
    }

    @Test fun allowLabelCountsDownThenUnlocks() {
        assertEquals("Allow 5 minutes · 0:05", SoftNoticeCopy.allowLabel(5_000))
        assertEquals("Allow 5 minutes · 0:05", SoftNoticeCopy.allowLabel(4_001))
        assertEquals("Allow 5 minutes · 0:30", SoftNoticeCopy.allowLabel(30_000))
        assertEquals("Allow 5 minutes", SoftNoticeCopy.allowLabel(0))
        assertEquals("Allow 5 minutes", SoftNoticeCopy.allowLabel(-1))
    }

    @Test fun timeLeftRoundsUpToWholeMinutes() {
        assertEquals("25 minutes left in this sprint", SoftNoticeCopy.timeLeft(24 * 60_000L + 1))
        assertEquals("1 minute left in this sprint", SoftNoticeCopy.timeLeft(1))
        assertEquals("This sprint is ending", SoftNoticeCopy.timeLeft(0))
    }

    @Test fun noticeNeverClaimsAnAppIsClosed() {
        val lines = listOf(SoftNoticeCopy.softNote, SoftNoticeCopy.homeLine(3), SoftNoticeCopy.homeLine(0)) +
            (1..4).map { SoftNoticeCopy.sentence("Chrome", "5 PM", it) }
        for (line in lines) {
            val lower = line.lowercase(Locale.ROOT)
            assertFalse(line, Regex("\\b(closed|closes|kill|killed|terminat)").containsMatchIn(lower.replace("doesn't close", "")))
        }
        assertTrue(SoftNoticeCopy.homeLine(3).contains("stays open"))
        assertEquals(3, SoftNoticeCopy.firmSeconds)
    }
}

class MomentumDisplayTest {
    @Test fun displayIsAWholeNumberLikeWindows() {
        assertEquals("0", Momentum.display(0.0))
        assertEquals("10", Momentum.display(10.4))
        assertEquals("11", Momentum.display(10.5))
        assertEquals("111", Momentum.display(111.3))
    }

    @Test fun changeShowsSignedDeltaAndNewScore() {
        assertEquals("+10 → 10", Momentum.change(0.0, 10.0))
        assertEquals("-17 → 83", Momentum.change(100.0, 83.0))
        assertEquals("0 → 0", Momentum.change(0.0, 0.0))
        assertEquals("+2 → 13", Momentum.change(10.0, 12.5))
    }

    @Test fun explanationIsWindowsWordForWord() {
        assertEquals(3, Momentum.explanation.size)
        assertTrue(Momentum.explanation[1].contains("about 15% and 2 points at Soft or Firm, 30% and 5 at Sealed"))
        assertTrue(Momentum.explanation[2].startsWith("Nothing happens while you are away."))
    }
}

class ShieldBestForTest {
    @Test fun bestForMatchesWindows() {
        assertEquals("Best for classes or light work.", ShieldCopy.bestFor(Shield.SOFT))
        assertEquals("Best for homework.", ShieldCopy.bestFor(Shield.FIRM))
        assertEquals("Best for exams and deep work.", ShieldCopy.bestFor(Shield.SEALED))
        assertEquals(listOf("Soft", "Firm", "Sealed"), Shield.entries.map(ShieldCopy::label))
    }
}
