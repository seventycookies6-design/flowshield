package com.basaltfocus.app.blocking

import android.content.*
import com.basaltfocus.app.BasaltApplication
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action !in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED)) return
        val pending = goAsync()
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                val repository = (context.applicationContext as BasaltApplication).repository
                repository.initialize()
                if (repository.recover()) {
                    try { context.startForegroundService(Intent(context, SprintService::class.java)) }
                    catch (_: RuntimeException) { SprintNotifications.recovery(context, repository.settings.first().active) }
                }
            } finally { pending.finish() }
        }
    }
}
