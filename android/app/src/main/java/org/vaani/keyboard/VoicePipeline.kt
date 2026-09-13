package org.vaani.keyboard

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.*
import java.util.Locale

/** STT boundary. A future JNI whisper.cpp engine can consume the same session contract. */
interface SttEngine { fun start(onText: (String) -> Unit, onError: (String) -> Unit); fun stop() }

/** Native engines (for example whisper.cpp through JNI) can implement this
 * contract and receive bounded mono 16 kHz PCM without JSON/base64 transport. */
interface PcmSttEngine {
    fun acceptPcm(samples: FloatArray)
    fun finish(onText: (String) -> Unit, onError: (String) -> Unit)
    fun cancel()
}

/** Cleanup is deliberately separate from recognition so an editor model can
 * be added without coupling it to the keyboard or microphone lifecycle. */
interface CleanupEngine { fun clean(raw: String): String }

/** Uses Android's on-device recognizer preference; it never sends text to a Vaani server. */
class OnDeviceSttEngine(private val context: Context, private val languageTag: String = Locale.getDefault().toLanguageTag(), private val level: (Float) -> Unit = {}, private val ready: () -> Unit = {}) : SttEngine {
    private var recognizer: SpeechRecognizer? = null
    override fun start(onText: (String) -> Unit, onError: (String) -> Unit) {
        if (android.os.Build.VERSION.SDK_INT < 31 || !SpeechRecognizer.isOnDeviceRecognitionAvailable(context)) { onError("On-device speech unavailable. Install an offline speech service/model in Android settings."); return }
        try {
        recognizer = SpeechRecognizer.createOnDeviceSpeechRecognizer(context).also { r ->
            r.setRecognitionListener(object : RecognitionListener {
                override fun onResults(b: Bundle) { onText(b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()) }
                override fun onError(e: Int) { onError("Speech recognition error ($e)") }
                override fun onReadyForSpeech(p: Bundle?) { ready() }; override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(v: Float) { level(v) }; override fun onBufferReceived(b: ByteArray?) = Unit
                override fun onEndOfSpeech() = Unit; override fun onPartialResults(b: Bundle?) = Unit
                override fun onEvent(t: Int, p: Bundle?) = Unit
            })
            r.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag)
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            })
        }
        } catch (_: RuntimeException) { cancel(); onError("Could not start on-device speech. Check microphone and speech settings.") }
    }
    override fun stop() { recognizer?.stopListening() }
    fun cancel() { recognizer?.cancel(); recognizer?.destroy(); recognizer = null }
}

/** Minimal-edit cleanup: punctuation/capitalization only; meaning and numbers survive. */
object ConservativeCleanup {
    fun apply(raw: String, enabled: Boolean): String {
        val text = raw.trim().replace(Regex("\\s+"), " ")
        if (!enabled || text.isEmpty()) return text
        val capitalized = text.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
        return if (capitalized.last() in ".!?।") capitalized else "$capitalized."
    }
}

class LocalConservativeCleanup(private val enabled: Boolean) : CleanupEngine {
    override fun clean(raw: String): String = ConservativeCleanup.apply(raw, enabled)
}
