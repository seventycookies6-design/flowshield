package com.basaltfocus.app.data

import android.content.Context
import android.app.NotificationManager
import android.app.NotificationManager.Policy
import com.basaltfocus.app.blocking.*
import androidx.room.Room
import com.basaltfocus.core.ActiveSprint
import com.basaltfocus.core.Shield
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowSystemClock
import java.time.Duration

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], manifest = Config.NONE, application = android.app.Application::class)
class RepositoryTest {
    private lateinit var database: HistoryDatabase
    private lateinit var store: SettingsStore
    private lateinit var repository: Repository
    private lateinit var scope: CoroutineScope
    private val now get() = System.currentTimeMillis()

    @Before fun prepare() = runBlocking {
        val context: Context = RuntimeEnvironment.getApplication()
        database = Room.inMemoryDatabaseBuilder(context, HistoryDatabase::class.java).allowMainThreadQueries().build()
        scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        store = SettingsStore(context)
        store.update { Settings() }
        repository = Repository(context, database, scope)
    }

    @After fun cleanup() { scope.cancel(); database.close() }

    @Test fun initializationPreservesTheOriginalTrialAcrossRestarts() = runBlocking {
        store.update { Settings(trialStartedAt = 1L) }
        repository.initialize(); repository.initialize()
        assertEquals(1L, repository.current().trialStartedAt)
    }

    @Test fun restoringASummaryPointerWithoutItsHistoryRowDoesNotTrapTheUser() = runBlocking {
        store.update { Settings(true, true, now, pendingSummaryId = "missing-after-restore") }
        assertFalse(repository.recover())
        assertNull(repository.current().pendingSummaryId)
    }

    @Test fun restoredLicenseNeedsItsOwnDeviceSeat() = runBlocking {
        store.update { Settings(licensed = true, licenseDeviceId = "another-device", licenseKey = "sample") }
        repository.initialize()
        assertFalse(repository.current().licensed)
        assertEquals("sample", repository.current().licenseKey)
    }

    @Test fun mistypingAnActivationDoesNotRevokeTheExistingLicense() = runBlocking {
        store.update { Settings(true, true, 1L, licensed = true, licenseDeviceId = repository.deviceId,
            licenseStatus = "active", licenseKey = "existing-sample") }
        repository.activate("a malformed replacement") { }
        assertTrue(repository.current().licensed)
        assertEquals("active", repository.current().licenseStatus)
        assertEquals("existing-sample", repository.current().licenseKey)
    }

    @Test fun sealedEditsAreRejectedByTheWriter() = runBlocking {
        val active = ActiveSprint("sealed", now, 25, Shield.SEALED)
        store.update { Settings(true, true, now, active = active) }
        assertNotNull(repository.setBlocked("com.android.chrome", true))
        assertTrue(repository.current().blockedPackages.isEmpty())
    }

    @Test fun criticalAppsCannotBeAddedEvenByDirectWriterCalls() = runBlocking {
        store.update { Settings(true, true, now) }
        assertNotNull(repository.setBlocked("com.android.settings", true))
        assertNotNull(repository.setBlocked("com.android.vending", true))
        assertTrue(repository.current().blockedPackages.isEmpty())
    }

    @Test fun expiredUnlicensedTrialRefusesStartAndEditing() = runBlocking {
        store.update { Settings(true, true, now - 7 * 86_400_000L) }
        assertNotNull(repository.start(25, Shield.SOFT))
        assertNotNull(repository.setBlocked("com.android.chrome", true))
        assertNull(repository.current().active)
    }

    @Test fun completedRecoveryAndReplayAwardExactlyOnce() = runBlocking {
        val active = ActiveSprint("completed", now - 1_500_000, 25, Shield.FIRM,
            lastSeenAt = now, watchedMillis = 1_500_000)
        store.update { Settings(true, true, now, active = active) }
        assertFalse(repository.recover())
        assertEquals(10.0, database.history().find(active.id)!!.momentumAfter, 0.0)
        // Reproduce process death after the Room commit but before active state was cleared.
        store.update { it.copy(active = active) }
        assertFalse(repository.recover())
        val rows = database.history().observe().first()
        assertEquals(1, rows.size)
        assertEquals(10.0, rows.single().momentumAfter, 0.0)
        assertEquals(active.id, repository.current().pendingSummaryId)
    }

    @Test fun interruptedRecoveryLeavesMomentumUnchanged() = runBlocking {
        database.history().insert(SprintRecord("before", now - 4_000_000, now - 3_000_000, 25,
            "SOFT", "Completed", 0.0, 10.0))
        val active = ActiveSprint("interrupted", now - 1_500_000, 25, Shield.SEALED, watchedMillis = 1000)
        store.update { Settings(true, true, now, active = active) }
        repository.recover()
        val row = database.history().find(active.id)!!
        assertEquals("Interrupted", row.outcome)
        assertEquals(10.0, row.momentumAfter, 0.0)
    }

    @Test fun summaryAfterTrialExpiryCanSaveOneLineAndClearItsGate() = runBlocking {
        val active = ActiveSprint("summary", now - 60_000, 1, Shield.SOFT, watchedMillis = 60_000)
        store.update { Settings(true, true, 1L, active = active) }
        repository.recover()
        repository.saveJournal(active.id, "  Read chapter three\nprivate second line  ")
        assertEquals("Read chapter three", database.history().find(active.id)!!.journal)
        assertNull(repository.current().pendingSummaryId)
    }

    @Test fun aLockedPhoneStillEarnsTheSprintWhileTheServiceRuns() = runBlocking {
        // The CPU sleeps through the whole sprint, so the service's last heartbeat is at the start.
        store.update { Settings(true, true, now, active = ActiveSprint("asleep", now - 26 * 60_000L, 25, Shield.FIRM)) }
        repository.startWatching()
        ShadowSystemClock.advanceBy(Duration.ofMinutes(26))
        assertTrue(repository.settleIfElapsed(now))
        assertEquals("Completed", database.history().find("asleep")!!.outcome)
    }

    @Test fun reopeningTheAppMidSprintKeepsTheServicesScreenOffCredit() = runBlocking {
        store.update { Settings(true, true, now, active = ActiveSprint("open", now - 10 * 60_000L, 25, Shield.SOFT)) }
        repository.startWatching()
        ShadowSystemClock.advanceBy(Duration.ofMinutes(10))
        assertTrue(repository.recover())
        assertTrue(repository.current().active!!.watchedMillis >= 9 * 60_000L)
    }

    @Test fun reopeningTheAppAfterALockedSprintEndedStillCompletesIt() = runBlocking {
        store.update { Settings(true, true, now, active = ActiveSprint("expired", now - 26 * 60_000L, 25, Shield.SOFT)) }
        repository.startWatching()
        ShadowSystemClock.advanceBy(Duration.ofMinutes(26))
        assertFalse(repository.recover())
        assertEquals("Completed", database.history().find("expired")!!.outcome)
    }

    private suspend fun repositoryWithSavedDnd(newProcess: Boolean = false): Pair<Repository, () -> DndState> {
        val policy = Policy(Policy.PRIORITY_CATEGORY_ALARMS, Policy.PRIORITY_SENDERS_ANY, Policy.PRIORITY_SENDERS_CONTACTS)
        var state = DndState(NotificationManager.INTERRUPTION_FILTER_ALL, policy)
        val snapshot = object : DndSnapshotStore {
            var value: DndSnapshot? = null
            override suspend fun read() = value
            override suspend fun write(snapshot: DndSnapshot) { value = snapshot }
            override suspend fun clear() { value = null }
        }
        val device = object : DndDevice {
            override val granted = true
            override val appScoped = false
            override fun current() = state
            override suspend fun setPolicy(policy: Policy) { state = state.copy(policy = policy) }
            override suspend fun setFilter(filter: Int) { state = state.copy(filter = filter) }
        }
        val dnd = DndController(device, snapshot)
        dnd.recoverOnce()
        dnd.start(true)
        return Repository(RuntimeEnvironment.getApplication(), database, scope,
            if (newProcess) DndController(device, snapshot) else dnd) to { state }
    }

    @Test fun cancellationInGraceRestoresDnd() = runBlocking {
        val (repo, state) = repositoryWithSavedDnd()
        store.update { Settings(true, true, now, active = ActiveSprint("cancel-dnd", now, 25, Shield.SOFT)) }
        assertNull(repo.end("cancel-dnd", null, null))
        assertNull(repo.current().active)
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, state().filter)
        assertEquals(Policy.PRIORITY_CATEGORY_ALARMS, state().policy.priorityCategories)
    }

    @Test fun timerCompletionRestoresDnd() = runBlocking {
        val (repo, state) = repositoryWithSavedDnd()
        store.update { Settings(true, true, now, active = ActiveSprint("elapsed-dnd", now - 60_000, 1, Shield.SOFT, watchedMillis = 60_000)) }
        assertTrue(repo.settleIfElapsed(now))
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, state().filter)
        assertEquals(Policy.PRIORITY_CATEGORY_ALARMS, state().policy.priorityCategories)
    }

    @Test fun startupRestoresSavedDndEvenIfAnUnexpiredSprintWillResume() = runBlocking {
        val (repo, state) = repositoryWithSavedDnd(newProcess = true)
        store.update { Settings(true, true, now, active = ActiveSprint("resumed-dnd", now, 25, Shield.SOFT)) }
        repo.initialize()
        assertTrue(repo.recover())
        assertEquals("resumed-dnd", repo.current().active!!.id)
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, state().filter)
        assertEquals(Policy.PRIORITY_CATEGORY_ALARMS, state().policy.priorityCategories)
    }
}
