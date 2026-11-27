package org.ad5x.converter

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.util.UUID

private const val THREE_MF = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"

class MainActivity : ComponentActivity() {
    private var selected by mutableStateOf<Uri?>(null)
    private var name by mutableStateOf("")
    private var result by mutableStateOf<File?>(null)
    private var busy by mutableStateOf(false)
    private var keepUnused by mutableStateOf(false)
    private var message by mutableStateOf("Choose a 3MF print project to begin.")
    private val open = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(::select) }
    private val save = registerForActivityResult(ActivityResultContracts.CreateDocument(THREE_MF)) { uri ->
        val file = result
        if (uri != null && file != null) export(file, uri)
    }
    private val saveReport = registerForActivityResult(ActivityResultContracts.CreateDocument("text/plain")) { uri ->
        val file = result?.let { File(it.path + ".report.txt") }
        if (uri != null && file != null) export(file, uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        @Suppress("DEPRECATION")
        if (intent.action == Intent.ACTION_SEND) (intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))?.let(::select)
        setContent { MaterialTheme { Surface(Modifier.fillMaxSize()) { Screen() } } }
    }

    private fun select(uri: Uri) {
        if (busy) return
        val display = runCatching {
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                if (it.moveToFirst()) it.getString(0) else null
            }
        }.getOrNull() ?: "project.3mf"
        if (!display.endsWith(".3mf", ignoreCase = true)) {
            message = "Please select a .3mf print project."
            return
        }
        selected = uri
        name = display.substringAfterLast('/').substringAfterLast('\\')
        result = null
        message = "Ready to convert. The source file will not be modified."
    }

    private fun convert() {
        val uri = selected ?: return
        if (busy) return
        val preserve = keepUnused
        val outputName = name.dropLast(4).replace(Regex("[^a-zA-Z0-9._ -]"), "_").take(120) + "_AD5X.3mf"
        busy = true
        result = null
        message = "Converting locally…"
        lifecycleScope.launch {
            try {
                val (out, details) = withContext(Dispatchers.IO) {
                    val dir = File(cacheDir, "converted/" + UUID.randomUUID()).apply { mkdirs() }
                    val src = File(dir, "source.3mf")
                    val template = File(dir, "ad5x_template.json")
                    val dst = File(dir, outputName)
                    try {
                        contentResolver.openInputStream(uri)?.use { input -> src.outputStream().use { input.copyTo(it) } }
                            ?: error("Unable to read selected file")
                        assets.open("ad5x_template.json").use { input -> template.outputStream().use { input.copyTo(it) } }
                        if (!Python.isStarted()) Python.start(AndroidPlatform(this@MainActivity))
                        val response = Python.getInstance().getModule("android_bridge").callAttr("convert_project", src.path, dst.path, template.path, preserve).toString()
                        dst to JSONObject(response)
                    } catch (e: Exception) {
                        dir.deleteRecursively()
                        throw e
                    } finally { src.delete(); template.delete() }
                }
                result = out
                message = buildString {
                    append(details.getString("summary"))
                    for (key in listOf("warnings", "notes")) {
                        val items = details.getJSONArray(key)
                        for (i in 0 until items.length()) {
                            append("\n\n")
                            if (key == "warnings") append("Warning: ")
                            append(items.getString(i))
                        }
                    }
                }
            } catch (e: Exception) { message = "Conversion failed: " + e.message }
            finally { busy = false }
        }
    }

    private fun export(file: File, uri: Uri) {
        if (busy) return
        busy = true
        lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    contentResolver.openOutputStream(uri, "w")?.use { output -> file.inputStream().use { it.copyTo(output) } }
                        ?: error("Cannot open destination")
                }
                message += "\n\nSaved " + file.name + "."
            } catch (e: Exception) { message += "\n\nSave failed: " + e.message }
            finally { busy = false }
        }
    }

    private fun share(file: File) {
        val uri = FileProvider.getUriForFile(this, "$packageName.files", file)
        val send = Intent(Intent.ACTION_SEND).apply {
            type = THREE_MF
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            clipData = android.content.ClipData.newRawUri(file.name, uri)
        }
        startActivity(Intent.createChooser(send, "Open converted project"))
    }

    @Composable private fun Screen() {
        Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("3MF-to-AD5X", style = MaterialTheme.typography.headlineMedium)
            Text("KilnOS · Adaptive Purge · 0.4 mm", style = MaterialTheme.typography.titleMedium)
            Text("Offline conversion. Your original files stay untouched.")
            OutlinedButton(onClick = { open.launch(arrayOf("*/*")) }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text(if (name.isEmpty()) "Select a 3MF project" else name) }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = keepUnused, onCheckedChange = { keepUnused = it }, enabled = !busy)
                Text("Keep unused filament entries")
            }
            Button(onClick = ::convert, enabled = selected != null && !busy, modifier = Modifier.fillMaxWidth()) { Text("Convert to AD5X") }
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            result?.let { file ->
                OutlinedButton(onClick = { save.launch(file.name) }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Save converted 3MF") }
                OutlinedButton(onClick = { share(file) }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Share to slicer") }
                OutlinedButton(onClick = { saveReport.launch(file.name + ".report.txt") }, enabled = !busy, modifier = Modifier.fillMaxWidth()) { Text("Save conversion report") }
            }
            Text(message)
        }
    }
}
