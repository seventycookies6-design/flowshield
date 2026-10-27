package com.basaltfocus.app.data

import com.basaltfocus.core.ActiveSprint
import com.basaltfocus.core.Shield
import org.junit.Assert.*
import org.junit.Test

class SettingsStoreTest {
    @Test fun `backup round trip preserves original trial active shield and history pointer`() {
        val original = Settings(true, true, 123L, setOf("org.example.calendar"),
            ActiveSprint("sprint-a", 456L, 25, Shield.SEALED, 900L, 444L), "previous",
            true, "test-key", "sample@example.invalid", "active", "device-hash", 789L, 2, 3)
        assertEquals(original, SettingsStore.decode(SettingsStore.encode(original)))
    }

    @Test fun `first launch does not silently invent a new trial before initialization`() {
        assertNull(SettingsStore.decode(null).trialStartedAt)
        assertFalse(SettingsStore.decode(null).initialized)
    }

    @Test fun `unset optional values remain absent`() {
        assertEquals(Settings(), SettingsStore.decode(SettingsStore.encode(Settings())))
    }
}
