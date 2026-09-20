package org.vaani.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

interface SttSession {
    fun start(onReady: () -> Unit, onResult: (String) -> Unit, onError: (String) -> Unit)
    fun stop()
    fun cancel()
}

/** Android's installed on-device recognizer is the usable no-network STT baseline. */
class OnDeviceStt(private val context: Context) : SttSession {
    private var recognizer: SpeechRecognizer? = null

    override fun start(onReady: () -> Unit, onResult: (String) -> Unit, onError: (String) -> Unit) {
        if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(context)) {
            onError("On-device speech is unavailable. Install an offline speech service first.")
            return
        }
        recognizer = SpeechRecognizer.createOnDeviceSpeechRecognizer(context).also { speech ->
            speech.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) = onReady()
                override fun onResults(results: Bundle) {
                    onResult(results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty())
                }
                override fun onError(error: Int) = onError("Speech recognition error ($error)")
                override fun onBeginningOfSpeech() = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() = Unit
                override fun onEvent(eventType: Int, params: Bundle?) = Unit
                override fun onPartialResults(partialResults: Bundle?) = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
            })
            speech.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            })
        }
    }

    override fun stop() = recognizer?.stopListening() ?: Unit
    override fun cancel() { recognizer?.cancel(); recognizer?.destroy(); recognizer = null }
}
