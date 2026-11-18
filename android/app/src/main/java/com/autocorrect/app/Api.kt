package com.autocorrect.app

import android.content.Context
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Saved settings: server address and the customer's access code. */
object Settings {
    private const val PREFS = "autocorrect"

    fun serverUrl(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString("server_url", null) ?: BuildConfig.DEFAULT_SERVER_URL

    fun accessCode(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("access_code", "") ?: ""

    fun save(ctx: Context, serverUrl: String, accessCode: String) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("server_url", serverUrl.trim().trimEnd('/'))
            .putString("access_code", accessCode.trim().uppercase())
            .apply()
    }
}

/** An error with a message that can be shown to the user as-is. */
class ApiException(val userMessage: String) : Exception(userMessage)

/** Talks to the Autocorrect server. Call from a background thread. */
object Api {

    fun transform(ctx: Context, text: String, action: String, target: String?): String {
        val body = JSONObject().put("text", text).put("action", action)
        if (target != null) body.put("target", target)
        return request(ctx, "POST", "/v1/transform", body).getString("result")
    }

    /** Checks the access code; returns the customer's name. */
    fun check(ctx: Context): String = request(ctx, "GET", "/v1/me", null).getString("name")

    private fun request(ctx: Context, method: String, path: String, body: JSONObject?): JSONObject {
        val conn = try {
            URL(Settings.serverUrl(ctx) + path).openConnection() as HttpURLConnection
        } catch (e: Exception) {
            throw ApiException(ctx.getString(R.string.err_network))
        }
        try {
            conn.requestMethod = method
            conn.connectTimeout = 15_000
            conn.readTimeout = 120_000
            conn.setRequestProperty("Authorization", "Bearer " + Settings.accessCode(ctx))
            conn.setRequestProperty("Accept", "application/json")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            if (code == 200) {
                val text = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
                return JSONObject(text)
            }
            throw ApiException(
                when (code) {
                    401 -> ctx.getString(R.string.err_code)
                    429 -> ctx.getString(R.string.err_limit)
                    413 -> ctx.getString(R.string.err_too_long)
                    503 -> ctx.getString(R.string.err_busy)
                    else -> ctx.getString(R.string.err_generic, code.toString())
                }
            )
        } catch (e: IOException) {
            throw ApiException(ctx.getString(R.string.err_network))
        } catch (e: org.json.JSONException) {
            throw ApiException(ctx.getString(R.string.err_generic, "json"))
        } finally {
            conn.disconnect()
        }
    }
}
