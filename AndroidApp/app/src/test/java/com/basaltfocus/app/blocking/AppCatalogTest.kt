package com.basaltfocus.app.blocking

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.pm.ResolveInfo
import android.content.pm.ServiceInfo
import android.view.accessibility.AccessibilityManager
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.util.ReflectionHelpers

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], manifest = Config.NONE, application = android.app.Application::class)
class AppCatalogTest {
    @Test fun anEnabledAccessibilityToolIsNeverBlockable() {
        val context: Context = RuntimeEnvironment.getApplication()
        val info = AccessibilityServiceInfo()
        ReflectionHelpers.setField(info, "mResolveInfo",
            ResolveInfo().apply { serviceInfo = ServiceInfo().apply { packageName = "org.example.screenreader" } })
        shadowOf(context.getSystemService(AccessibilityManager::class.java)).setEnabledAccessibilityServiceList(listOf(info))
        assertTrue("org.example.screenreader" in AppCatalog.protected(context))
    }
}
