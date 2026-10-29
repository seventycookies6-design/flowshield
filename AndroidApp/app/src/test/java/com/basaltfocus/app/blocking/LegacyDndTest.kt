package com.basaltfocus.app.blocking

import android.app.NotificationManager
import android.app.NotificationManager.Policy
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26], manifest = Config.NONE, application = android.app.Application::class)
class LegacyDndTest {
    @Suppress("DEPRECATION") // API 26 uses the original screen-off visual effect flag.
    @Test fun minimumSdkCanSaveApplyAndRestoreEveryConfigurablePolicyField() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val manager = context.getSystemService(NotificationManager::class.java)
        org.robolectric.Shadows.shadowOf(manager).setNotificationPolicyAccessGranted(true)
        val original = Policy(Policy.PRIORITY_CATEGORY_REMINDERS or Policy.PRIORITY_CATEGORY_EVENTS,
            Policy.PRIORITY_SENDERS_CONTACTS, Policy.PRIORITY_SENDERS_ANY, Policy.SUPPRESSED_EFFECT_SCREEN_OFF)
        manager.notificationPolicy = original
        manager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_NONE)
        val file = java.io.File(context.noBackupFilesDir, "legacy-dnd-test.json")
        val store = FileDndSnapshotStore(file)
        val device = AndroidDndDevice(context)
        DndController(device, store).start(true)
        assertEquals(NotificationManager.INTERRUPTION_FILTER_PRIORITY, manager.currentInterruptionFilter)
        assertEquals(Policy.PRIORITY_SENDERS_STARRED, manager.notificationPolicy.priorityCallSenders)
        assertEquals(Policy.PRIORITY_SENDERS_STARRED, manager.notificationPolicy.priorityMessageSenders)
        DndController(device, FileDndSnapshotStore(file)).recoverOnce()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_NONE, manager.currentInterruptionFilter)
        assertEquals(original, manager.notificationPolicy)
        assertNull(store.read())
    }
}
