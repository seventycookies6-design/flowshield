package com.basaltfocus.app.data

import android.content.Context
import android.os.Build
import android.os.SystemClock
import android.provider.Settings as AndroidSettings
import androidx.room.withTransaction
import com.basaltfocus.app.BuildConfig
import com.basaltfocus.app.blocking.AppCatalog
import com.basaltfocus.app.blocking.Permissions
import com.basaltfocus.app.license.DeviceIdentity
import com.basaltfocus.app.license.LicenseClient
import com.basaltfocus.app.license.LicenseCachePolicy
import com.basaltfocus.core.*
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** One process-wide writer; the history row is committed before clearing active state.
 * Replaying after process death finds the same primary key and never awards twice. */
class Repository(private val context: Context, private val database: HistoryDatabase,
                 private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)) {
    private val lock = Mutex()
    private val licenseLock = Mutex()
    private val store = SettingsStore(context)
    val settings = store.flow.stateIn(scope, SharingStarted.Eagerly, Settings())
    val history = database.history().observe().stateIn(scope, SharingStarted.Eagerly, emptyList())
    val deviceId: String by lazy {
        DeviceIdentity.hash(AndroidSettings.Secure.getString(context.contentResolver, AndroidSettings.Secure.ANDROID_ID) ?: "unavailable")
    }

    suspend fun current(): Settings = store.flow.first()

    suspend fun initialize() = lock.withLock {
        store.update { s -> s.copy(initialized = true,
            trialStartedAt = s.trialStartedAt ?: System.currentTimeMillis(),
            // Auto Backup must not copy one phone's license seat to another.
            licensed = s.licensed && s.licenseDeviceId == deviceId) }
    }

    suspend fun finishOnboarding() = store.update { it.copy(onboardingDone = true) }

    suspend fun start(minutes: Int, shield: Shield): String? = lock.withLock {
        val s = store.flow.first()
        SprintLength.error(minutes, BuildConfig.DEBUG)?.let { return@withLock it }
        if (!s.initialized || !TrialPolicy.hasAccess(s.licensed, s.trialStartedAt, System.currentTimeMillis()))
            return@withLock "Enter your license key to start a sprint."
        if (s.active != null || s.pendingSummaryId != null) return@withLock "Finish the current sprint or summary first."
        if (!Permissions.canBlock(context)) return@withLock "Allow Usage Access and display over other apps first."
        val now = System.currentTimeMillis()
        val a = ActiveSprint(UUID.randomUUID().toString(), now, minutes, shield)
        store.update { it.copy(active = a) }
        null
    }

    suspend fun setBlocked(packageName: String, blocked: Boolean): String? = lock.withLock {
        val s = store.flow.first()
        if (!TrialPolicy.hasAccess(s.licensed, s.trialStartedAt, System.currentTimeMillis()))
            return@withLock "Enter your license key to edit the blocklist."
        if (!BlockPolicy.blocklistEditable(s.active?.shield)) return@withLock "Sealed keeps this list locked until the sprint ends."
        if (BlockPolicy.neverBlock(packageName, context.packageName, AppCatalog.protected(context)))
            return@withLock "Essential apps always stay available."
        store.update { it.copy(blockedPackages = if (blocked) it.blockedPackages + packageName else it.blockedPackages - packageName) }
        null
    }

    /** Monotonic time of the service's last look, while it runs in this process; null otherwise. */
    @Volatile private var watchedAtRealtime: Long? = null

    fun startWatching() { watchedAtRealtime = SystemClock.elapsedRealtime() }
    fun stopWatching() { watchedAtRealtime = null }

    suspend fun heartbeat(now: Long) = lock.withLock { creditWatching(now) }

    /** A locked phone sleeps the CPU while the service stays alive, so that whole gap was watched.
     * Monotonic time bounds it, so a changed wall clock can't add credit. Callers hold the lock. */
    private suspend fun creditWatching(now: Long) {
        val since = watchedAtRealtime ?: return
        val realtime = SystemClock.elapsedRealtime()
        store.update { s -> s.copy(active = s.active?.heartbeat(now, realtime - since + 1_000)) }
        watchedAtRealtime = realtime
    }

    /** Called on boot/start before heartbeats, so offline time is not counted. */
    suspend fun recover(): Boolean = lock.withLock {
        val s = store.flow.first()
        val a = s.active ?: run {
            // Backup restores can contain the preferences pointer without its Room row.
            // Preserve real summaries, but do not leave the user on an endless loading gate.
            if (s.pendingSummaryId != null && database.history().find(s.pendingSummaryId) == null)
                store.update { it.copy(pendingSummaryId = null) }
            return@withLock false
        }
        when (a.resumeDecision(System.currentTimeMillis())) {
            ResumeDecision.RESUME -> {
                // A new activity while the service still runs must not drop its screen-off credit.
                if (watchedAtRealtime != null) creditWatching(System.currentTimeMillis())
                else store.update { it.copy(active = a.copy(lastSeenAt = maxOf(a.lastSeenAt, System.currentTimeMillis()))) }
                true
            }
            ResumeDecision.DISCARD -> { store.update { it.copy(active = null) }; false }
            ResumeDecision.COMPLETED -> { record(a, "Completed"); false }
            ResumeDecision.INTERRUPTED -> { record(a, "Interrupted"); false }
        }
    }

    suspend fun settleIfElapsed(now: Long): Boolean = lock.withLock {
        creditWatching(now)
        val a = store.flow.first().active ?: return@withLock true
        if (now < a.endsAt) return@withLock false
        record(a, if (a.resumeDecision(now) == ResumeDecision.COMPLETED) "Completed" else "Interrupted")
        true
    }

    suspend fun end(sprintId: String, requestAtMonotonic: Long?, phrase: String?): String? = lock.withLock {
        val a = store.flow.first().active ?: return@withLock null
        if (a.id != sprintId) return@withLock "This sprint has already changed."
        val now = System.currentTimeMillis()
        if (now >= a.endsAt) {
            creditWatching(now)
            val watched = store.flow.first().active ?: return@withLock null
            record(watched, if (watched.resumeDecision(now) == ResumeDecision.COMPLETED) "Completed" else "Interrupted")
            return@withLock null
        }
        if (!SprintPolicy.canEnd(a, now, requestAtMonotonic, SystemClock.elapsedRealtime(), phrase))
            return@withLock "Wait for the countdown and check the phrase."
        if (EndSprintPolicy.flowFor(a.shield, now - a.startedAt) == EndFlow.CANCEL) {
            store.update { it.copy(active = null) }
        } else record(a, "Ended early")
        null
    }

    private suspend fun record(a: ActiveSprint, outcome: String) {
        database.withTransaction {
            if (database.history().find(a.id) == null) {
                val before = database.history().latestMomentum() ?: 0.0
                val after = when (outcome) {
                    "Completed" -> Momentum.afterCompletion(before, a.plannedMinutes)
                    "Ended early" -> EndSprintPolicy.momentumAfterEndingEarly(before, a.shield)
                    else -> before
                }
                val ended = if (outcome == "Interrupted") a.startedAt + a.watchedMillis.coerceIn(0, a.endsAt - a.startedAt)
                    else minOf(System.currentTimeMillis(), a.endsAt)
                database.history().insert(SprintRecord(a.id, a.startedAt, ended, a.plannedMinutes,
                    a.shield.name, outcome, before, after))
            }
        }
        store.update { it.copy(active = null, pendingSummaryId = a.id) }
    }

    suspend fun saveJournal(id: String, text: String) = lock.withLock {
        val s = store.flow.first()
        if (s.pendingSummaryId != id) return@withLock
        database.history().journal(id, text.lineSequence().firstOrNull().orEmpty().trim().take(280))
        store.update { it.copy(pendingSummaryId = null) }
    }

    suspend fun activate(input: String, onProgress: (String) -> Unit): String = checkLicense(input, false, onProgress)

    private suspend fun checkLicense(input: String, refreshing: Boolean, onProgress: (String) -> Unit): String = licenseLock.withLock {
        // Read refresh credentials after acquiring the lock so an older refresh cannot
        // revoke a different license the user just activated.
        val credential = if (refreshing) current().let { it.licenseKey.ifBlank { it.licenseEmail } } else input
        if (credential.isBlank() && refreshing) return@withLock ""
        val result = LicenseClient(BuildConfig.LICENSE_BASE_URL).validate(credential, deviceId,
            "${Build.MANUFACTURER} ${Build.MODEL}", onProgress)
        lock.withLock {
            store.update { s ->
                // As on Windows, trying a mistyped replacement is not a revocation of
                // the existing license. Only a refresh of cached credentials can revoke it.
                val preserve = s.licensed && !result.isPro && !refreshing
                s.copy(
                licensed = preserve || LicenseCachePolicy.keepAccess(s.licensed, result),
                licenseKey = if (result.isPro) result.licenseKey ?: credential.trim().takeUnless { '@' in it }.orEmpty() else s.licenseKey,
                licenseEmail = if (result.isPro) result.email ?: credential.trim().takeIf { '@' in it }.orEmpty() else s.licenseEmail,
                licenseDeviceId = if (result.isPro) deviceId else s.licenseDeviceId,
                licenseStatus = if (result.definitive && !preserve) result.status else s.licenseStatus,
                licenseCheckedAt = if (result.isPro) System.currentTimeMillis() else s.licenseCheckedAt,
                deviceCount = if (result.definitive) result.deviceCount else s.deviceCount,
                deviceLimit = if (result.definitive) result.deviceLimit else s.deviceLimit,
            ) }
        }
        result.message
    }

    suspend fun refreshLicense() {
        checkLicense("", true) { }
    }
}
