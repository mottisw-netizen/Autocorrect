package com.autocorrect.app

import android.app.Activity
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.TextView
import kotlin.concurrent.thread

/** Setup screen: choose how to connect (access code or own key), check it, and try the feature. */
class MainActivity : Activity() {

    private lateinit var mode: RadioGroup
    private lateinit var code: EditText
    private lateinit var server: EditText
    private lateinit var preset: Spinner
    private lateinit var baseUrl: EditText
    private lateinit var apiKey: EditText
    private lateinit var model: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        mode = findViewById(R.id.mode)
        code = findViewById(R.id.code)
        server = findViewById(R.id.server)
        preset = findViewById(R.id.preset)
        baseUrl = findViewById(R.id.base_url)
        apiKey = findViewById(R.id.api_key)
        model = findViewById(R.id.model)
        val status = findViewById<TextView>(R.id.status)
        val save = findViewById<Button>(R.id.save)

        // Load saved values.
        code.setText(Settings.accessCode(this))
        server.setText(Settings.serverUrl(this))
        apiKey.setText(Settings.apiKey(this))
        model.setText(Settings.model(this))
        baseUrl.setText(Settings.baseUrl(this))
        preset.adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_dropdown_item, Preset.values().map { it.label }
        )
        preset.setSelection(Settings.preset(this).ordinal)
        mode.check(if (Settings.mode(this) == Settings.MODE_OWN_KEY) R.id.mode_own_key else R.id.mode_server)

        // Customers normally only need the code; hide the server field when it's preconfigured.
        if (BuildConfig.DEFAULT_SERVER_URL.startsWith("https://") &&
            !BuildConfig.DEFAULT_SERVER_URL.contains("YOUR-SERVER")
        ) {
            server.visibility = View.GONE
            findViewById<View>(R.id.server_label).visibility = View.GONE
        }

        mode.setOnCheckedChangeListener { _, _ -> updateSections() }
        preset.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) = updateSections()
            override fun onNothingSelected(p: AdapterView<*>?) = Unit
        }
        updateSections()

        save.setOnClickListener {
            val ownKey = mode.checkedRadioButtonId == R.id.mode_own_key
            Settings.save(
                this, mapOf(
                    "mode" to if (ownKey) Settings.MODE_OWN_KEY else Settings.MODE_SERVER,
                    "access_code" to code.text.toString().uppercase(),
                    "server_url" to server.text.toString().trimEnd('/'),
                    "preset" to Preset.values()[preset.selectedItemPosition].id,
                    "base_url" to baseUrl.text.toString().trimEnd('/'),
                    "api_key" to apiKey.text.toString(),
                    "model" to model.text.toString(),
                )
            )
            status.text = getString(R.string.checking)
            save.isEnabled = false
            thread {
                val message = try {
                    when (val p = Settings.provider(this)) {
                        is ServerProvider -> getString(R.string.connected, p.check())
                        is OpenAICompatibleProvider -> getString(R.string.connected_key, p.check())
                        else -> ""
                    }
                } catch (e: ApiException) {
                    e.userMessage
                }
                runOnUiThread {
                    if (!isDestroyed) {
                        status.text = message
                        save.isEnabled = true
                    }
                }
            }
        }
    }

    private fun updateSections() {
        val ownKey = mode.checkedRadioButtonId == R.id.mode_own_key
        findViewById<View>(R.id.section_server).visibility = if (ownKey) View.GONE else View.VISIBLE
        findViewById<View>(R.id.section_own_key).visibility = if (ownKey) View.VISIBLE else View.GONE
        val selected = Preset.values()[preset.selectedItemPosition.coerceAtLeast(0)]
        val custom = selected == Preset.CUSTOM
        findViewById<View>(R.id.base_url).visibility = if (custom) View.VISIBLE else View.GONE
        findViewById<View>(R.id.base_url_label).visibility = if (custom) View.VISIBLE else View.GONE
        apiKey.hint = selected.keyHint
    }
}
