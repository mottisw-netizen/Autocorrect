package com.autocorrect.app

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import kotlin.concurrent.thread

/**
 * Opened from the text-selection menu ("תרגום ותיקון") in any app.
 * Shows three big buttons; the chosen result replaces the selected text.
 * If the app doesn't allow replacing (read-only text), the result is shown with a Copy button.
 */
class ProcessTextActivity : Activity() {

    private var text: String = ""
    private var readOnly = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_process)

        text = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString() ?: ""
        readOnly = intent.getBooleanExtra(Intent.EXTRA_PROCESS_TEXT_READONLY, false)
        findViewById<TextView>(R.id.preview).text = text

        when {
            text.isBlank() -> showMessage(getString(R.string.no_text))
            !Settings.isConfigured(this) -> showMessage(getString(R.string.no_code), openSettings = true)
            else -> {
                findViewById<Button>(R.id.btn_english).setOnClickListener { run(Action.translate("English")) }
                findViewById<Button>(R.id.btn_hebrew).setOnClickListener { run(Action.translate("Hebrew")) }
                findViewById<Button>(R.id.btn_fix).setOnClickListener { run(Action.fix()) }
            }
        }
    }

    private fun run(action: Action) {
        findViewById<View>(R.id.actions).visibility = View.GONE
        findViewById<View>(R.id.progress).visibility = View.VISIBLE
        thread {
            val outcome = try {
                Result.success(Settings.provider(this).transform(text, action))
            } catch (e: ApiException) {
                Result.failure(e)
            }
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                findViewById<View>(R.id.progress).visibility = View.GONE
                outcome.fold(
                    onSuccess = { deliver(it) },
                    onFailure = { showMessage((it as ApiException).userMessage) },
                )
            }
        }
    }

    private fun deliver(result: String) {
        if (!readOnly) {
            // Hand the new text back to the app; it replaces the selection.
            setResult(RESULT_OK, Intent().putExtra(Intent.EXTRA_PROCESS_TEXT, result))
            finish()
            return
        }
        showMessage(getString(R.string.readonly_hint))
        findViewById<TextView>(R.id.result).apply {
            this.text = result
            visibility = View.VISIBLE
        }
        findViewById<Button>(R.id.btn_primary).apply {
            setText(R.string.copy)
            visibility = View.VISIBLE
            setOnClickListener {
                val cm = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("Autocorrect", result))
                Toast.makeText(this@ProcessTextActivity, R.string.copied, Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    private fun showMessage(message: String, openSettings: Boolean = false) {
        findViewById<View>(R.id.actions).visibility = View.GONE
        findViewById<TextView>(R.id.message).apply {
            text = message
            visibility = View.VISIBLE
        }
        findViewById<View>(R.id.footer).visibility = View.VISIBLE
        findViewById<Button>(R.id.btn_secondary).setOnClickListener { finish() }
        findViewById<Button>(R.id.btn_primary).apply {
            if (openSettings) {
                setText(R.string.open_settings)
                setOnClickListener {
                    startActivity(Intent(this@ProcessTextActivity, MainActivity::class.java))
                    finish()
                }
            } else {
                visibility = View.GONE
            }
        }
    }
}
