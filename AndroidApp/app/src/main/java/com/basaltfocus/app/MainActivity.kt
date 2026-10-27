package com.basaltfocus.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.lifecycleScope
import androidx.window.layout.FoldingFeature
import androidx.window.layout.WindowInfoTracker
import com.basaltfocus.app.ui.BasaltApp
import com.basaltfocus.app.ui.BasaltTheme
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val hinge = MutableStateFlow<FoldingFeature?>(null)
    private val model: MainViewModel by lazy { androidx.lifecycle.ViewModelProvider(this)[MainViewModel::class.java] }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        lifecycleScope.launch {
            WindowInfoTracker.getOrCreate(this@MainActivity).windowLayoutInfo(this@MainActivity).collect {
                hinge.value = it.displayFeatures.filterIsInstance<FoldingFeature>().firstOrNull { fold -> fold.isSeparating }
            }
        }
        setContent { BasaltTheme { BasaltApp(model, hinge) } }
    }
    override fun onResume() { super.onResume(); model.onResume() }
}
