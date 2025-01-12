package com.example.automationapp

import android.os.Bundle
import android.util.Log
import androidx.appcompat.app.AppCompatActivity
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import okhttp3.MediaType.Companion.toMediaType

class MainActivity : AppCompatActivity() {
    private val TAG = "MainActivity"
    private val client = OkHttpClient()
    private val serverUrl = "http://192.168.1.220:5001"  // Your IP address here
    private var sessionId: String? = null  // Store the session ID

    override fun onCreate(savedInstanceState: Bundle?) {
        try {
            super.onCreate(savedInstanceState)
            setContentView(R.layout.activity_main)

            val startSessionButton = findViewById<Button>(R.id.startSessionButton)
            val commandInput = findViewById<EditText>(R.id.commandInput)
            val executeButton = findViewById<Button>(R.id.executeButton)
            val outputText = findViewById<TextView>(R.id.outputText)

            startSessionButton.setOnClickListener {
                Log.d(TAG, "Start Session button clicked")
                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        val request = Request.Builder()
                            .url("$serverUrl/start_session")
                            .post(okhttp3.RequestBody.create(null, ByteArray(0)))
                            .build()

                        client.newCall(request).execute().use { response ->
                            val responseBody = response.body?.string()
                            Log.d(TAG, "Response: $responseBody")
                            
                            // Parse the session ID from response
                            responseBody?.let {
                                val json = org.json.JSONObject(it)
                                sessionId = json.optString("session_id")
                            }
                            
                            runOnUiThread {
                                if (response.isSuccessful) {
                                    Toast.makeText(this@MainActivity, "Session started successfully", Toast.LENGTH_SHORT).show()
                                    outputText.text = "Session started: $responseBody"
                                } else {
                                    Toast.makeText(this@MainActivity, "Failed to start session", Toast.LENGTH_SHORT).show()
                                    outputText.text = "Error: ${response.code}"
                                }
                            }
                        }
                    } catch (e: IOException) {
                        Log.e(TAG, "Error starting session", e)
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                            outputText.text = "Error: ${e.message}"
                        }
                    }
                }
            }

            executeButton.setOnClickListener {
                if (sessionId == null) {
                    Toast.makeText(this, "Please start a session first", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }

                val command = commandInput.text.toString()
                if (command.isEmpty()) {
                    Toast.makeText(this, "Please enter a command", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }

                CoroutineScope(Dispatchers.IO).launch {
                    try {
                        val requestBody = okhttp3.RequestBody.create(
                            "application/json".toMediaType(),
                            """{"command": "$command", "session_id": "$sessionId"}"""
                        )

                        val request = Request.Builder()
                            .url("$serverUrl/execute_command")
                            .post(requestBody)
                            .build()

                        client.newCall(request).execute().use { response ->
                            val responseBody = response.body?.string()
                            Log.d(TAG, "Execute Response: $responseBody")
                            
                            runOnUiThread {
                                if (response.isSuccessful) {
                                    outputText.text = "Command executed: $responseBody"
                                } else {
                                    outputText.text = "Error executing command: ${response.code}"
                                }
                            }
                        }
                    } catch (e: IOException) {
                        Log.e(TAG, "Error executing command", e)
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                            outputText.text = "Error executing command: ${e.message}"
                        }
                    }
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "Error in onCreate", e)
            Toast.makeText(this, "Error: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }
} 