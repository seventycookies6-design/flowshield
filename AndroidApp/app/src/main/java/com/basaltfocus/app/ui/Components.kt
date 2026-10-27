package com.basaltfocus.app.ui

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.unit.dp

fun Modifier.keyboardRing(): Modifier = composed {
    var focused by remember { mutableStateOf(false) }
    val color = MaterialTheme.colorScheme.primary
    this.onFocusChanged { focused = it.isFocused }.then(
        if (focused) Modifier.border(2.dp, color, MaterialTheme.shapes.small) else Modifier)
}

@Composable
fun Action(label: String, enabled: Boolean = true, primary: Boolean = false, onClick: () -> Unit) {
    if (primary) Button(onClick, Modifier.fillMaxWidth().heightIn(min = 48.dp).keyboardRing(), enabled = enabled,
        shape = MaterialTheme.shapes.small) { Text(label) }
    else OutlinedButton(onClick, Modifier.fillMaxWidth().heightIn(min = 48.dp).keyboardRing(), enabled = enabled,
        shape = MaterialTheme.shapes.small) { Text(label) }
}

@Composable
fun Page(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(title, style = MaterialTheme.typography.headlineLarge)
        content()
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
fun Panel(content: @Composable ColumnScope.() -> Unit) {
    Surface(shape = MaterialTheme.shapes.medium, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}
