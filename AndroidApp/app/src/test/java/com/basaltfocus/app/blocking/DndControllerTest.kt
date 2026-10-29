package com.basaltfocus.app.blocking

import android.app.NotificationManager
import android.app.NotificationManager.Policy
import android.content.Context
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], manifest = Config.NONE, application = android.app.Application::class)
class DndControllerTest {
    private val originalPolicy = Policy(Policy.PRIORITY_CATEGORY_ALARMS or Policy.PRIORITY_CATEGORY_REPEAT_CALLERS,
        Policy.PRIORITY_SENDERS_CONTACTS, Policy.PRIORITY_SENDERS_ANY,
        Policy.SUPPRESSED_EFFECT_PEEK, Policy.CONVERSATION_SENDERS_IMPORTANT)
    private val original get() = DndState(NotificationManager.INTERRUPTION_FILTER_ALARMS, originalPolicy)

    private class MemoryStore : DndSnapshotStore {
        var saved: DndSnapshot? = null
        override suspend fun read() = saved
        override suspend fun write(snapshot: DndSnapshot) { saved = snapshot }
        override suspend fun clear() { saved = null }
    }
    private class Device(var state: DndState, val store: DndSnapshotStore) : DndDevice {
        override var granted = true
        override var appScoped = false
        var writes = 0
        var reads = 0
        override fun current(): DndState { check(granted); reads++; return state }
        override suspend fun setPolicy(policy: Policy) {
            check(store.read() != null) { "Prior state must be durable before any system write" }
            writes++; state = state.copy(policy = policy)
        }
        override suspend fun setFilter(filter: Int) {
            check(store.read() != null)
            writes++; state = state.copy(filter = filter)
        }
    }

    @Test fun sprintEndRestoresTheOriginalFilterAndEveryPolicyField() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        val controller = DndController(device, store)
        controller.start(true)
        assertEquals(NotificationManager.INTERRUPTION_FILTER_PRIORITY, device.state.filter)
        assertEquals(Policy.PRIORITY_CATEGORY_CALLS or Policy.PRIORITY_CATEGORY_MESSAGES, device.state.policy.priorityCategories)
        assertEquals(Policy.PRIORITY_SENDERS_STARRED, device.state.policy.priorityCallSenders)
        assertEquals(Policy.PRIORITY_SENDERS_STARRED, device.state.policy.priorityMessageSenders)
        assertEquals(Policy.CONVERSATION_SENDERS_NONE, device.state.policy.priorityConversationSenders)
        controller.finish()
        assertEquals(original, device.state)
        assertNull(store.saved)
    }

    @Test fun nextProcessRestoresTheDurableSnapshotEvenWhileTheSprintCanResume() = runBlocking {
        val context: Context = RuntimeEnvironment.getApplication()
        val file = java.io.File(context.noBackupFilesDir, "dnd-process-test")
        file.delete()
        val disk = FileDndSnapshotStore(file)
        val device = Device(original, disk)
        DndController(device, disk).start(true)
        assertNotEquals(original, device.state)
        // Recreate both the controller and disk store, as after process death or boot.
        DndController(device, FileDndSnapshotStore(file)).recoverOnce()
        assertEquals(original, device.state)
        assertNull(FileDndSnapshotStore(file).read())
    }

    @Test fun noAccessLeavesTheSystemAndSavedStateAlone() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store).apply { granted = false }
        val controller = DndController(device, store)
        controller.start(true); controller.finish(); controller.recoverOnce()
        assertEquals(original, device.state); assertEquals(0, device.writes); assertEquals(0, device.reads); assertNull(store.saved)
    }

    @Test fun settingOffTouchesNothing() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        DndController(device, store).start(false)
        assertEquals(original, device.state); assertEquals(0, device.writes); assertEquals(0, device.reads); assertNull(store.saved)
    }

    @Test fun aUserFilterChangeIsPreservedAndTheSnapshotIsCleared() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        val controller = DndController(device, store)
        controller.start(true)
        val userState = DndState(NotificationManager.INTERRUPTION_FILTER_NONE, originalPolicy)
        device.state = userState
        controller.finish()
        assertEquals(userState, device.state); assertNull(store.saved)
    }

    @Test fun aUserPolicyChangeAtTheSameFilterIsAlsoPreserved() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        val controller = DndController(device, store)
        controller.start(true)
        device.state = device.state.copy(policy = originalPolicy)
        val userState = device.state
        controller.finish()
        assertEquals(userState, device.state); assertNull(store.saved)
    }

    @Test fun switchingBackToTheOriginalFilterIsStillAUserOverride() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        val controller = DndController(device, store)
        controller.start(true)
        device.state = device.state.copy(filter = original.filter)
        val userState = device.state
        controller.finish()
        assertEquals(userState, device.state); assertNull(store.saved)
    }

    @Suppress("DEPRECATION") // Android returns these redundant aliases alongside modern flags.
    @Test fun systemNormalizedVisualEffectAliasesStillMatchOurPolicyForRestoration() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        val controller = DndController(device, store)
        controller.start(true)
        val applied = device.state.policy
        device.state = device.state.copy(policy = Policy(applied.priorityCategories,
            applied.priorityCallSenders, applied.priorityMessageSenders,
            applied.suppressedVisualEffects or Policy.SUPPRESSED_EFFECT_SCREEN_ON, applied.priorityConversationSenders))
        controller.finish()
        assertEquals(original, device.state); assertNull(store.saved)
    }

    @Test fun failureToSavePriorStatePreventsAnySystemWrites() = runBlocking {
        val store = object : DndSnapshotStore {
            override suspend fun read(): DndSnapshot? = null
            override suspend fun write(snapshot: DndSnapshot) { throw java.io.IOException("Disk full") }
            override suspend fun clear() { }
        }
        val device = Device(original, store)
        DndController(device, store).start(true)
        assertEquals(original, device.state); assertEquals(0, device.writes)
    }

    @Test fun deathBetweenPolicyAndFilterWritesStillRestoresBoth() = runBlocking {
        val store = MemoryStore()
        val applied = DndController.starredPolicy(Policy.SUPPRESSED_EFFECT_PEEK)
        store.saved = DndSnapshot(original, applied, false, DndPhase.PREPARING)
        val device = Device(original.copy(policy = applied), store)
        DndController(device, store).recoverOnce()
        assertEquals(original, device.state); assertNull(store.saved)
    }

    @Test fun deathDuringRestorationCanRetryAfterTheFilterHasAlreadyReturned() = runBlocking {
        val store = MemoryStore()
        val applied = DndController.starredPolicy(Policy.SUPPRESSED_EFFECT_PEEK)
        store.saved = DndSnapshot(original, applied, false, DndPhase.RESTORING)
        val device = Device(original.copy(policy = applied), store)
        DndController(device, store).recoverOnce()
        assertEquals(original, device.state); assertNull(store.saved)
    }

    @Test fun deathBeforeAnySystemChangeJustClearsThePendingSnapshot() = runBlocking {
        val store = MemoryStore()
        store.saved = DndSnapshot(original, DndController.starredPolicy(Policy.SUPPRESSED_EFFECT_PEEK), false)
        val device = Device(original, store)
        DndController(device, store).recoverOnce()
        assertEquals(original, device.state); assertEquals(0, device.writes); assertNull(store.saved)
    }

    @Test fun revokedAccessKeepsTheSnapshotUntilRestorationIsPossible() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        val controller = DndController(device, store)
        controller.start(true); device.granted = false
        val writes = device.writes
        controller.finish()
        assertEquals(writes, device.writes); assertNotNull(store.saved)
        device.granted = true; controller.finish()
        assertEquals(original, device.state); assertNull(store.saved)
    }

    @Test fun repeatedInitializationDoesNotUndoThisProcessesRunningSprint() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store)
        val controller = DndController(device, store)
        controller.recoverOnce(); controller.start(true); controller.recoverOnce()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_PRIORITY, device.state.filter)
        assertNotNull(store.saved)
    }

    @Test fun modernAndroidDeactivatesOnlyBasaltsRuleRatherThanReactivatingThePriorFilter() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store).apply { appScoped = true }
        val controller = DndController(device, store)
        controller.start(true); controller.finish()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, device.state.filter)
        assertEquals(originalPolicy, device.state.policy); assertNull(store.saved)
    }

    @Test fun modernAndroidDeactivatesBasaltsRuleEvenIfAnotherModeChangedTheGlobalFilter() = runBlocking {
        val store = MemoryStore(); val device = Device(original, store).apply { appScoped = true }
        val controller = DndController(device, store)
        controller.start(true)
        device.state = device.state.copy(filter = NotificationManager.INTERRUPTION_FILTER_NONE)
        controller.finish()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, device.state.filter)
        assertNull(store.saved)
    }
}
