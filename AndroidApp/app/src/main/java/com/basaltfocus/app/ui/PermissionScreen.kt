package com.basaltfocus.app.ui

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import com.basaltfocus.app.blocking.Permissions

enum class PermissionStep { USAGE, OVERLAY, NOTIFICATIONS }

@Composable
fun PermissionScreen(step: PermissionStep, revision: Int, onContinue: () -> Unit) {
    val context = LocalContext.current
    var detail by remember(step) { mutableStateOf("") }
    var resultRevision by remember { mutableIntStateOf(0) }
    val notification = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { resultRevision++ }
    val granted = remember(step, revision, resultRevision) { when (step) {
        PermissionStep.USAGE -> Permissions.usage(context)
        PermissionStep.OVERLAY -> Permissions.overlay(context)
        PermissionStep.NOTIFICATIONS -> Permissions.notifications(context)
    } }
    val title = when (step) {
        PermissionStep.USAGE -> "Usage Access"
        PermissionStep.OVERLAY -> "Display over other apps"
        PermissionStep.NOTIFICATIONS -> "Sprint notifications"
    }
    Page(title) {
        Text(when (step) {
            PermissionStep.USAGE -> "Basalt reads which app is in front while your sprint runs. It compares the app's package name with your blocklist. App activity never leaves your phone."
            PermissionStep.OVERLAY -> "Basalt displays a focus notice over an app you chose to block. This permission does not read the app's screen or messages. Your blocklist and notices never leave your phone."
            PermissionStep.NOTIFICATIONS -> "Basalt shows time left in an ongoing sprint notification. This permission does not read your other notifications. Sprint information stays on your phone."
        })
        Text(when (step) {
            PermissionStep.USAGE -> "On the next system screen, choose Basalt and allow Usage Access. Without it, Basalt cannot detect blocked apps."
            PermissionStep.OVERLAY -> "On the next system screen, choose Basalt and allow display over other apps. Firm and Sealed also use this permission to return you to the home screen."
            PermissionStep.NOTIFICATIONS -> "You may decline. Your sprint can still run; Android may only show the service in its active-app controls. A recovery notification after a restart needs this permission."
        })
        Text(if (granted) "Allowed" else "Not allowed", style = MaterialTheme.typography.titleMedium)
        if (detail.isNotEmpty()) Text(detail)
        Action("Open $title", primary = !granted) {
            runCatching {
                when (step) {
                    PermissionStep.USAGE -> context.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                    PermissionStep.OVERLAY -> context.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")))
                    PermissionStep.NOTIFICATIONS -> if (Build.VERSION.SDK_INT >= 33 && !granted)
                        notification.launch(Manifest.permission.POST_NOTIFICATIONS)
                    else context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
                }
            }.onFailure { detail = "This phone couldn't open that screen. Open Android Settings and find Basalt's permissions." }
        }
        Action(if (granted) "Continue" else "Not now", primary = granted, onClick = onContinue)
        Text("Battery saver can pause blocking on some phones. If that happens, open the system battery settings.", style = MaterialTheme.typography.bodySmall)
        Action("System battery settings") {
            runCatching { context.startActivity(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS)) }
                .onFailure { detail = "Open Android Settings, then Battery." }
        }
    }
}
