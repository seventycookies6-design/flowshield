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
        val until = java.text.DateFormat.getTimeInstance(java.text.DateFormat.SHORT).format(java.util.Date(sprint.endsAt))
        val tryNumber = if (sprint.shield == Shield.SOFT) soft.tries else 1
        text("BASALT · ${ShieldCopy.label(sprint.shield).uppercase()} SHIELD", 12f)
        text(SoftNoticeCopy.sentence(label, until, tryNumber), 28f).apply {
            typeface = context.resources.getFont(R.font.inter_semibold)
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        text(SoftNoticeCopy.timeLeft(sprint.endsAt - System.currentTimeMillis()), 16f)
        fun button(label: String, primary: Boolean, click: () -> Unit): Button = Button(context).apply {
            text = label; isAllCaps = false; minHeight = dp(48)
            typeface = context.resources.getFont(R.font.inter_medium); textSize = 15f
            setTextColor(tokens.native(if (primary) "primary-ink" else "text"))
            val enabledState = intArrayOf(android.R.attr.state_enabled)
            backgroundTintList = android.content.res.ColorStateList(arrayOf(enabledState, intArrayOf()),
                intArrayOf(tokens.native(if (primary) "primary" else "surface-2"), tokens.native("bg-soft")))
            setTextColor(android.content.res.ColorStateList(arrayOf(enabledState, intArrayOf()),
                intArrayOf(tokens.native(if (primary) "primary-ink" else "text"), tokens.native("text-faint"))))
            setOnClickListener { click() }
            layout.addView(this, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(16) })
        }
        if (sprint.shield == Shield.SOFT) {
            text(SoftNoticeCopy.tryLine(tryNumber), 14f).setTextColor(tokens.native("text-muted"))
            button("Back to focus", primary = true) { soft.backToWork(packageName, System.currentTimeMillis()); onHome(); hide() }
            val allow = button(SoftNoticeCopy.allowLabel(1), primary = false) {
                soft.allowFiveMinutes(packageName, System.currentTimeMillis()); hide()
            }
            text(SoftNoticeCopy.softNote, 14f).setTextColor(tokens.native("text-muted"))
            val deadline = android.os.SystemClock.elapsedRealtime() + SoftOverlayPolicy.allowWaitMillis(tryNumber)
            allow.isEnabled = false
            countdown = scope.launch {
                while (isActive) {
                    val left = (deadline - android.os.SystemClock.elapsedRealtime()).coerceAtLeast(0)
                    allow.isEnabled = left == 0L
                    allow.text = SoftNoticeCopy.allowLabel(left)
                    if (left == 0L) break
                    delay(200)
                }
            }
        } else {
            val line = text(SoftNoticeCopy.homeLine(SoftNoticeCopy.firmSeconds), 14f)
            line.setTextColor(tokens.native("text-muted"))
            button("Go home now", primary = true) { onHome(); hide() }
            countdown = scope.launch {
                for (left in SoftNoticeCopy.firmSeconds downTo 1) {
                    line.text = SoftNoticeCopy.homeLine(left)
                    delay(1000)
                }
                line.text = SoftNoticeCopy.homeLine(0)
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
