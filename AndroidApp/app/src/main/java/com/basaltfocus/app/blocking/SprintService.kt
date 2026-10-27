package com.basaltfocus.app.blocking

import android.app.*
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.*
import com.basaltfocus.app.BasaltApplication
import com.basaltfocus.core.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow

class SprintService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val repository get() = (application as BasaltApplication).repository
    private lateinit var overlay: NoticeOverlay
    private var loop: Job? = null
    private val soft = SoftOverlayPolicy()
    private var foreground: String? = null
    private var handledForeground: String? = null
    private var cursor = System.currentTimeMillis() - 15_000

    override fun onCreate() {
        super.onCreate()
        overlay = NoticeOverlay(this, scope)
        val n = SprintNotifications.notification(this)
        if (Build.VERSION.SDK_INT >= 34) startForeground(SprintNotifications.RUNNING_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(SprintNotifications.RUNNING_ID, n)
        status.value = "Running"
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (loop?.isActive == true) return START_STICKY
        loop = scope.launch {
            try {
                repository.initialize()
                if (!repository.recover()) { stopSelf(); return@launch }
                val protected = AppCatalog.protected(this@SprintService)
                val usage = getSystemService(UsageStatsManager::class.java)
                var lastHeartbeat = SystemClock.elapsedRealtime()
                var sprintId: String? = null
                while (isActive) {
                    val now = System.currentTimeMillis()
                    if (repository.settleIfElapsed(now)) { stopSelf(); break }
                    val state = repository.current()
                    val active = state.active
                    if (active == null) { stopSelf(); break }
                    if (sprintId != active.id) {
                        soft.reset(); overlay.hide(); handledForeground = null
                        sprintId = active.id
                    }
                    if (SystemClock.elapsedRealtime() - lastHeartbeat >= 1000) {
                        repository.heartbeat(now)
                        lastHeartbeat = SystemClock.elapsedRealtime()
                        getSystemService(NotificationManager::class.java).notify(SprintNotifications.RUNNING_ID,
                            SprintNotifications.notification(this@SprintService, active))
                    }
                    if (!Permissions.canBlock(this@SprintService)) {
                        overlay.hide(); status.value = "Blocking paused: check permissions"
                        delay(650); continue
                    }
                    status.value = "Running"
                    if (getSystemService(KeyguardManager::class.java).isKeyguardLocked) {
                        overlay.hide(); foreground = null; handledForeground = null; soft.leftForeground()
                        delay(650); continue
                    }
                    val events = try { usage.queryEvents(cursor, now) }
                    catch (_: SecurityException) {
                        overlay.hide(); status.value = "Blocking paused: check permissions"
                        delay(650); continue
                    }
                    val event = UsageEvents.Event()
                    while (events.hasNextEvent()) {
                        events.getNextEvent(event)
                        @Suppress("DEPRECATION")
                        when (event.eventType) {
                            UsageEvents.Event.MOVE_TO_FOREGROUND -> foreground = event.packageName
                            UsageEvents.Event.MOVE_TO_BACKGROUND -> if (foreground == event.packageName) foreground = null
                        }
                    }
                    cursor = now
                    if (handledForeground != foreground) {
                        handledForeground = null
                        if (overlay.showingPackage != foreground) overlay.hide()
                    }
                    val decision = BlockPolicy.decision(true, active.shield, foreground, state.blockedPackages,
                        packageName, protected, soft, now)
                    if (decision == BlockDecision.NONE) {
                        if (foreground == null || foreground !in state.blockedPackages ||
                            BlockPolicy.neverBlock(foreground!!, packageName, protected)) overlay.hide()
                    } else if (handledForeground != foreground && overlay.showingPackage == null) {
                        val target = foreground!!
                        handledForeground = target
                        val label = runCatching { packageManager.getApplicationLabel(packageManager.getApplicationInfo(target, 0)).toString() }.getOrDefault("This app")
                        overlay.show(target, label, active, soft) {
                            runCatching { startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                        }
                    }
                    // Soft allowance expiry is a fresh decision even without an app switch.
                    if (active.shield == Shield.SOFT && overlay.showingPackage == null && foreground != null &&
                        soft.isQuiet(foreground!!, now)) handledForeground = null
                    delay(650)
                }
            } finally { overlay.hide() }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null
    override fun onDestroy() {
        overlay.hide(); scope.cancel(); soft.reset(); status.value = "Paused"
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
    companion object { val status = MutableStateFlow("Paused") }
}
