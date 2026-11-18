package com.autocorrect.app

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import kotlin.concurrent.thread

/** Setup screen: enter the access code, check it, and try the feature. */
class MainActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val code = findViewById<EditText>(R.id.code)
        val server = findViewById<EditText>(R.id.server)
        val status = findViewById<TextView>(R.id.status)
        val save = findViewById<Button>(R.id.save)

        code.setText(Settings.accessCode(this))
        server.setText(Settings.serverUrl(this))

        // Customers normally only need the code; hide the server field when it's preconfigured.
        if (BuildConfig.DEFAULT_SERVER_URL.startsWith("https://") &&
            !BuildConfig.DEFAULT_SERVER_URL.contains("YOUR-SERVER")
        ) {
            server.visibility = android.view.View.GONE
            findViewById<TextView>(R.id.server_label).visibility = android.view.View.GONE
        }

        save.setOnClickListener {
            Settings.save(this, server.text.toString(), code.text.toString())
            status.text = getString(R.string.checking)
            save.isEnabled = false
            thread {
                val message = try {
                    getString(R.string.connected, Api.check(this))
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
}
