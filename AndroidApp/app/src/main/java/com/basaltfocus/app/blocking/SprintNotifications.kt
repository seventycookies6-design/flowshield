package com.basaltfocus.app.blocking

import android.app.*
import android.content.Context
import android.content.Intent
import com.basaltfocus.app.MainActivity
import com.basaltfocus.app.R
import com.basaltfocus.core.ActiveSprint

object SprintNotifications {
    const val RUNNING_ID = 1
    private const val FINISHED_ID = 3
    private const val CHANNEL = "focus_sprint"
    fun createChannel(context: Context) {
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Focus sprint", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Sprint time left and recovery. No sounds."
                setSound(null, null); enableVibration(false); setShowBadge(false)
            })
    }
    fun notification(context: Context, sprint: ActiveSprint? = null, resume: Boolean = false): Notification {
        createChannel(context)
        val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val remaining = sprint?.let { ((it.endsAt - System.currentTimeMillis()).coerceAtLeast(0) + 999) / 1000 }
        val text = when {
            resume -> "Tap to resume your sprint. Blocking is paused."
            remaining != null -> "%d:%02d left · %s shield".format(remaining / 60, remaining % 60,
                sprint.shield.name.lowercase().replaceFirstChar { it.titlecase() })
            else -> "Restoring your sprint…"
        }
        return Notification.Builder(context, CHANNEL).setSmallIcon(R.drawable.basalt_mark)
            .setContentTitle("Basalt").setContentText(text).setContentIntent(open)
            .setOngoing(!resume).setOnlyAlertOnce(true).setShowWhen(false)
            .setCategory(Notification.CATEGORY_PROGRESS).build()
    }
    /** The sprint ran its full length while Basalt was in the background. */
    fun finished(context: Context) {
        if (!Permissions.notifications(context)) return
        createChannel(context)
        val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        context.getSystemService(NotificationManager::class.java).notify(FINISHED_ID,
            Notification.Builder(context, CHANNEL).setSmallIcon(R.drawable.basalt_mark)
                .setContentTitle("Sprint finished").setContentText("Open Basalt to note what moved.")
                .setContentIntent(open).setAutoCancel(true).build())
    }

    fun recovery(context: Context, sprint: ActiveSprint?) {
        if (Permissions.notifications(context)) context.getSystemService(NotificationManager::class.java)
            .notify(2, notification(context, sprint, resume = true))
    }
}
