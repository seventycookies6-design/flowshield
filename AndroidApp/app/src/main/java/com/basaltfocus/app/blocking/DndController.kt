package com.basaltfocus.app.blocking

import android.app.NotificationManager
import android.app.NotificationManager.Policy
import android.content.Context
import android.os.Build
import android.util.AtomicFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.json.JSONException
import java.io.File
import java.io.FileNotFoundException
import java.io.IOException

data class DndState(val filter: Int, val policy: Policy)
enum class DndPhase { PREPARING, ACTIVE, RESTORING }
data class DndSnapshot(val previous: DndState, val applied: Policy, val appScoped: Boolean,
    val phase: DndPhase = DndPhase.PREPARING)

interface DndSnapshotStore {
    suspend fun read(): DndSnapshot?
    suspend fun write(snapshot: DndSnapshot)
    suspend fun clear()
}

interface DndDevice {
    val granted: Boolean
    val appScoped: Boolean
    fun current(): DndState
    suspend fun setPolicy(policy: Policy)
    suspend fun setFilter(filter: Int)
}

class DndController(private val device: DndDevice, private val store: DndSnapshotStore) {
    private var recovered = false

    /** Repository serializes every call with its sprint writer lock. */
    suspend fun recoverOnce() = bestEffort {
        if (recovered) return@bestEffort
        finish()
        recovered = store.read() == null
    }

    suspend fun start(enabled: Boolean) = bestEffort {
        if (!enabled || !device.granted) return@bestEffort
        // Never overwrite a prior snapshot, including one awaiting re-granted access.
        finish()
        if (store.read() != null) return@bestEffort
        val previous = device.current()
        val policy = starredPolicy(previous.policy.suppressedVisualEffects)
        val snapshot = DndSnapshot(previous, policy, device.appScoped)
        store.write(snapshot)
        device.setPolicy(policy)
        device.setFilter(NotificationManager.INTERRUPTION_FILTER_PRIORITY)
        store.write(snapshot.copy(phase = DndPhase.ACTIVE))
    }

    suspend fun finish() = bestEffort {
        val saved = store.read() ?: return@bestEffort
        if (!device.granted) return@bestEffort
        val current = device.current()
        val canRestore = samePolicy(current.policy, saved.applied) &&
            (current.filter == NotificationManager.INTERRUPTION_FILTER_PRIORITY ||
                (saved.phase != DndPhase.ACTIVE && current.filter == saved.previous.filter))
        if (saved.appScoped || canRestore) store.write(saved.copy(phase = DndPhase.RESTORING))
        if (saved.appScoped) {
            // On Android 15+ these setters affect Basalt's implicit AutomaticZenRule,
            // not the user's global mode. ALL deactivates only our rule, even when
            // another mode currently makes the global filter NONE or ALARMS.
            device.setFilter(NotificationManager.INTERRUPTION_FILTER_ALL)
            if (samePolicy(current.policy, saved.applied)) device.setPolicy(saved.previous.policy)
        } else if (canRestore) {
            // Also covers death between the policy/filter writes or during restoration.
            // Change the filter first so a retry can still recognize our policy.
            device.setFilter(saved.previous.filter)
            device.setPolicy(saved.previous.policy)
        }
        // A different filter or policy is a user override; never reapply our DND.
        store.clear()
    }

    private suspend fun bestEffort(action: suspend () -> Unit) {
        try { action() }
        catch (_: SecurityException) { /* Revocation can race the access check; retry later. */ }
        catch (_: IOException) { /* A failed durable save must not change the system. */ }
    }

    companion object {
        fun starredPolicy(visualEffects: Int): Policy = if (Build.VERSION.SDK_INT >= 30)
            Policy(Policy.PRIORITY_CATEGORY_CALLS or Policy.PRIORITY_CATEGORY_MESSAGES,
                Policy.PRIORITY_SENDERS_STARRED, Policy.PRIORITY_SENDERS_STARRED,
                visualEffects, Policy.CONVERSATION_SENDERS_NONE)
        else Policy(Policy.PRIORITY_CATEGORY_CALLS or Policy.PRIORITY_CATEGORY_MESSAGES,
            Policy.PRIORITY_SENDERS_STARRED, Policy.PRIORITY_SENDERS_STARRED, visualEffects)

        private fun samePolicy(a: Policy, b: Policy): Boolean =
            a.priorityCategories == b.priorityCategories && a.priorityCallSenders == b.priorityCallSenders &&
                a.priorityMessageSenders == b.priorityMessageSenders && visualEffects(a) == visualEffects(b) &&
                (Build.VERSION.SDK_INT < 30 || a.priorityConversationSenders == b.priorityConversationSenders)

        @Suppress("DEPRECATION")
        private fun visualEffects(policy: Policy): Int {
            var effects = policy.suppressedVisualEffects
            if (Build.VERSION.SDK_INT < 28) return effects
            // Android adds the old SCREEN_ON/OFF aliases to the policy it returns.
            // Compare their meaning, so normalization is not mistaken for a user edit.
            if (effects and Policy.SUPPRESSED_EFFECT_SCREEN_OFF != 0)
                effects = effects or Policy.SUPPRESSED_EFFECT_FULL_SCREEN_INTENT or
                    Policy.SUPPRESSED_EFFECT_LIGHTS or Policy.SUPPRESSED_EFFECT_AMBIENT
            if (effects and Policy.SUPPRESSED_EFFECT_SCREEN_ON != 0)
                effects = effects or Policy.SUPPRESSED_EFFECT_PEEK
            return effects and (Policy.SUPPRESSED_EFFECT_SCREEN_ON or Policy.SUPPRESSED_EFFECT_SCREEN_OFF).inv()
        }

        fun forContext(context: Context) = DndController(AndroidDndDevice(context),
            FileDndSnapshotStore(File(context.noBackupFilesDir, "sprint-dnd.json")))
    }
}

class AndroidDndDevice(context: Context) : DndDevice {
    private val manager = context.getSystemService(NotificationManager::class.java)
    override val granted get() = manager.isNotificationPolicyAccessGranted
    override val appScoped get() = Build.VERSION.SDK_INT >= 35
    override fun current() = DndState(manager.currentInterruptionFilter, manager.notificationPolicy)
    override suspend fun setPolicy(policy: Policy) { manager.notificationPolicy = policy }
    override suspend fun setFilter(filter: Int) { manager.setInterruptionFilter(filter) }
}

/** Device-local recovery state must never follow Auto Backup onto another phone.
 * AtomicFile fsyncs the complete snapshot before any NotificationManager mutation.
 * Store all public, configurable policy fields, not Parcel's version-dependent bytes. */
class FileDndSnapshotStore(file: File) : DndSnapshotStore {
    private val atomic = AtomicFile(file)
    override suspend fun read(): DndSnapshot? = withContext(Dispatchers.IO) {
        val raw = try { atomic.openRead().bufferedReader().use { it.readText() } }
            catch (_: FileNotFoundException) { return@withContext null }
        try {
            val json = JSONObject(raw)
            DndSnapshot(DndState(json.getInt("filter"), decodePolicy(json.getJSONObject("previous"))),
                decodePolicy(json.getJSONObject("applied")), json.getBoolean("appScoped"),
                DndPhase.valueOf(json.getString("phase")))
        } catch (failure: JSONException) { throw IOException("Unreadable DND snapshot", failure) }
        catch (failure: IllegalArgumentException) { throw IOException("Unknown DND snapshot phase", failure) }
    }

    override suspend fun write(snapshot: DndSnapshot) = withContext(Dispatchers.IO) {
        val bytes = JSONObject().apply {
            put("filter", snapshot.previous.filter)
            put("previous", encodePolicy(snapshot.previous.policy))
            put("applied", encodePolicy(snapshot.applied))
            put("appScoped", snapshot.appScoped)
            put("phase", snapshot.phase.name)
        }.toString().toByteArray(Charsets.UTF_8)
        val stream = atomic.startWrite()
        try { stream.write(bytes); atomic.finishWrite(stream) }
        catch (failure: Throwable) { atomic.failWrite(stream); throw failure }
    }

    override suspend fun clear() = withContext(Dispatchers.IO) { atomic.delete() }

    private fun encodePolicy(policy: Policy) = JSONObject().apply {
        put("categories", policy.priorityCategories); put("calls", policy.priorityCallSenders)
        put("messages", policy.priorityMessageSenders); put("visualEffects", policy.suppressedVisualEffects)
        if (Build.VERSION.SDK_INT >= 30) put("conversations", policy.priorityConversationSenders)
    }

    private fun decodePolicy(json: JSONObject): Policy = if (Build.VERSION.SDK_INT >= 30)
        Policy(json.getInt("categories"), json.getInt("calls"), json.getInt("messages"),
            json.getInt("visualEffects"), json.optInt("conversations", Policy.CONVERSATION_SENDERS_NONE))
    else Policy(json.getInt("categories"), json.getInt("calls"), json.getInt("messages"), json.getInt("visualEffects"))
}
