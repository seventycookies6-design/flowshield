package com.basaltfocus.app.blocking

import android.content.Context
import android.graphics.PixelFormat
import android.view.*
import android.widget.*
import com.basaltfocus.app.R
import com.basaltfocus.app.ui.TokenPalette
import com.basaltfocus.core.*
import kotlinx.coroutines.*

/** A user-dismissible application overlay, never an activity or lock screen. */
class NoticeOverlay(private val context: Context, private val scope: CoroutineScope) {
    private val windows = context.getSystemService(WindowManager::class.java)
    private var view: ScrollView? = null
    private var countdown: Job? = null
    var showingPackage: String? = null
        private set

    fun show(packageName: String, label: String, sprint: ActiveSprint, soft: SoftOverlayPolicy,
             onHome: () -> Unit) {
        hide()
        val tokens = TokenPalette.system(context)
        val density = context.resources.displayMetrics.density
        fun dp(n: Int) = (n * density).toInt()
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(24), dp(48), dp(24), dp(48))
            setBackgroundColor(tokens.native("surface"))
        }
        fun text(value: String, size: Float): TextView = TextView(context).apply {
            text = value; textSize = size; setTextColor(tokens.native("text"))
            typeface = context.resources.getFont(R.font.inter_regular)
            setPadding(0, dp(8), 0, dp(8))
            layout.addView(this, LinearLayout.LayoutParams(-1, -2))
        }
        val name = sprint.shield.name.lowercase().replaceFirstChar { it.titlecase() }
        text("Basalt · $name shield", 18f)
        text("$label is on your blocklist", 30f)
        val seconds = ((sprint.endsAt - System.currentTimeMillis()).coerceAtLeast(0) + 999) / 1000
        text("%d:%02d left in this sprint".format(seconds / 60, seconds % 60), 18f)
        fun button(label: String, click: () -> Unit): Button = Button(context).apply {
            text = label; isAllCaps = false; minHeight = dp(48)
            typeface = context.resources.getFont(R.font.inter_medium); textSize = 13f
            setTextColor(tokens.native("primary-ink")); backgroundTintList = android.content.res.ColorStateList.valueOf(tokens.native("primary"))
            setOnClickListener { click() }
            layout.addView(this, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(16) })
        }
        if (sprint.shield == Shield.SOFT) {
            text("You can go back to focus or keep using this app for five minutes.", 14f)
            button("Back to focus") { soft.backToWork(packageName, System.currentTimeMillis()); onHome(); hide() }
            val allow = button("Allow 5 minutes") { soft.allowFiveMinutes(packageName, System.currentTimeMillis()); hide() }
            val deadline = android.os.SystemClock.elapsedRealtime() + SoftOverlayPolicy.allowWaitMillis(soft.tries)
            countdown = scope.launch {
                while (isActive) {
                    val left = ((deadline - android.os.SystemClock.elapsedRealtime() + 999) / 1000).coerceAtLeast(0)
                    allow.isEnabled = left == 0L
                    allow.text = if (left == 0L) "Allow 5 minutes" else "Allow 5 minutes · ${left}s"
                    if (left == 0L) break
                    delay(200)
                }
            }
        } else {
            val line = text("Back to focus in 3 seconds. This app stays open.", 14f)
            button("Back to focus now") { onHome(); hide() }
            countdown = scope.launch {
                for (left in 3 downTo 1) {
                    line.text = "Back to focus in $left seconds. This app stays open."
                    delay(1000)
                }
                onHome(); hide()
            }
        }
        val scroll = ScrollView(context).apply { isFillViewport = true; addView(layout) }
        val params = WindowManager.LayoutParams(-1, -1, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.OPAQUE)
        try { windows.addView(scroll, params); view = scroll; showingPackage = packageName }
        catch (_: RuntimeException) { countdown?.cancel(); showingPackage = null }
    }

    fun hide() {
        countdown?.cancel(); countdown = null
        view?.let { runCatching { windows.removeViewImmediate(it) } }
        view = null; showingPackage = null
    }
}
