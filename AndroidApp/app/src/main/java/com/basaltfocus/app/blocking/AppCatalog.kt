package com.basaltfocus.app.blocking

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable
import android.telecom.TelecomManager
import android.view.accessibility.AccessibilityManager
import com.basaltfocus.core.BlockPolicy

data class LaunchableApp(val packageName: String, val label: String, val icon: Drawable)

object AppCatalog {
    @Suppress("DEPRECATION")
    fun protected(context: Context): Set<String> {
        val pm = context.packageManager
        val intents = listOf(
            Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME),
            Intent(Intent.ACTION_DIAL), Intent("android.intent.action.CALL_EMERGENCY"),
            Intent(android.provider.Settings.ACTION_SETTINGS),
        )
        return buildSet {
            add(context.packageName)
            addAll(listOf("android", "com.android.systemui", "com.android.settings", "com.android.vending",
                "com.google.android.permissioncontroller", "com.android.permissioncontroller",
                "com.android.phone", "com.android.server.telecom", "com.google.android.safetyhub"))
            intents.forEach { intent -> pm.queryIntentActivities(intent, PackageManager.MATCH_ALL).forEach { add(it.activityInfo.packageName) } }
            context.getSystemService(TelecomManager::class.java)?.defaultDialerPackage?.let { add(it) }
            // Any accessibility tool the user has turned on, not only those BlockPolicy names.
            context.getSystemService(AccessibilityManager::class.java)
                ?.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
                ?.forEach { add(it.resolveInfo.serviceInfo.packageName) }
        }
    }

    @Suppress("DEPRECATION")
    fun launchable(context: Context): List<LaunchableApp> {
        val pm = context.packageManager
        val protected = protected(context)
        return pm.queryIntentActivities(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0)
            .distinctBy { it.activityInfo.packageName }
            .filterNot { BlockPolicy.neverBlock(it.activityInfo.packageName, context.packageName, protected) }
            .map { LaunchableApp(it.activityInfo.packageName, it.loadLabel(pm).toString(), it.loadIcon(pm)) }
            .sortedBy { it.label.lowercase() }
    }
}
