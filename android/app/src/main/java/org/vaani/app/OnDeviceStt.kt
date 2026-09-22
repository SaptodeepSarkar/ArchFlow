package org.vaani.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.content.pm.PackageManager
import dev.ffmpegkit.whisper.Whisper
import dev.ffmpegkit.whisper.WhisperConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

interface SttSession {
    fun start(onReady: () -> Unit, onResult: (String) -> Unit, onError: (String) -> Unit, onRms: (Float) -> Unit = {})
    fun stop()
    fun cancel()
}

/** Android's installed on-device recognizer is the usable no-network STT baseline. */
class OnDeviceStt(private val context: Context) : SttSession {
    private var recognizer: SpeechRecognizer? = null

    override fun start(onReady: () -> Unit, onResult: (String) -> Unit, onError: (String) -> Unit, onRms: (Float) -> Unit) {
        if (context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            onError("Microphone permission is not granted")
            return
        }
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
                override fun onRmsChanged(rmsdB: Float) = onRms(((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
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

/** File-backed whisper.cpp session used when a user-installed model pack exists. */
class NativeWhisperStt(private val context: Context, private val modelFile: File) : SttSession {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var recorder: AudioRecord? = null
    private var recording = false
    private var job: Job? = null

    override fun start(onReady: () -> Unit, onResult: (String) -> Unit, onError: (String) -> Unit, onRms: (Float) -> Unit) {
        if (context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            onError("Microphone permission is not granted")
            return
        }
        if (!modelFile.isFile) { onError("Embedded STT model is missing"); return }
        val minimum = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, ENCODING)
        if (minimum <= 0) { onError("Audio input is unavailable"); return }
        val audio = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE, CHANNEL_CONFIG, ENCODING, minimum * 2)
        if (audio.state != AudioRecord.STATE_INITIALIZED) { audio.release(); onError("Audio input could not start"); return }
        recorder = audio
        recording = true
        onReady()
        job = scope.launch {
            val pcm = ByteArrayOutputStream()
            val buffer = ByteArray(minimum)
            try {
                audio.startRecording()
                val started = System.currentTimeMillis()
                while (recording && System.currentTimeMillis() - started < MAX_RECORDING_MS) {
                    val read = audio.read(buffer, 0, buffer.size)
                    if (read > 0) {
                        pcm.write(buffer, 0, read)
                        onRms(rmsLevel(buffer, read))
                    }
                }
                audio.stop()
                audio.release()
                recorder = null
                if (pcm.size() < MIN_AUDIO_BYTES) {
                    withContext(Dispatchers.Main) { onError("No speech detected") }
                    return@launch
                }
                val wav = File.createTempFile("vaani-stt-", ".wav", context.cacheDir)
                writeWav(wav, pcm.toByteArray())
                try {
                    val model = Whisper.loadModel(context, modelFile.absolutePath)
                    try {
                        val result = Whisper.transcribe(model, wav.absolutePath, WhisperConfig(language = "en", threads = 2))
                        withContext(Dispatchers.Main) { onResult(result.text.trim()) }
                    } finally { Whisper.releaseModel(model) }
                } finally { wav.delete() }
            } catch (error: Throwable) {
                // Keep logs diagnostic-only: never write audio or recognised
                // text.  The exception class is enough to distinguish an
                // AudioRecord/ABI/model failure on a physical device.
                Log.w("VaaniStt", "Native STT session failed: ${error.javaClass.simpleName}")
                withContext(Dispatchers.Main) { onError("Embedded STT failed") }
            }
        }
    }

    override fun stop() { recording = false }

    override fun cancel() {
        recording = false
        recorder?.runCatching { stop() }
        recorder?.release()
        recorder = null
        job?.cancel()
        scope.cancel()
    }

    private fun writeWav(file: File, pcm: ByteArray) {
        DataOutputStream(FileOutputStream(file)).use { out ->
            fun intLE(value: Int) = out.write(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(value).array())
            fun shortLE(value: Short) = out.write(ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(value).array())
            out.writeBytes("RIFF"); intLE(36 + pcm.size); out.writeBytes("WAVE")
            out.writeBytes("fmt "); intLE(16); shortLE(1); shortLE(1); intLE(SAMPLE_RATE)
            intLE(SAMPLE_RATE * 2); shortLE(2); shortLE(16); out.writeBytes("data"); intLE(pcm.size); out.write(pcm)
        }
    }

    private fun rmsLevel(buffer: ByteArray, length: Int): Float {
        var sum = 0.0
        var samples = 0
        var index = 0
        while (index + 1 < length) {
            val sample = ((buffer[index + 1].toInt() shl 8) or (buffer[index].toInt() and 0xff)).toShort().toInt()
            sum += sample.toDouble() * sample.toDouble()
            samples++
            index += 2
        }
        if (samples == 0) return 0f
        return (kotlin.math.sqrt(sum / samples) / Short.MAX_VALUE).toFloat().coerceIn(0f, 1f)
    }

    companion object {
        const val SAMPLE_RATE = 16_000
        const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        const val MAX_RECORDING_MS = 90_000L
        const val MIN_AUDIO_BYTES = SAMPLE_RATE / 2
        /** The model alone is insufficient: the installed APK must carry the JNI library for this ABI. */
        fun isAvailable(context: Context): Boolean =
            File(context.applicationInfo.nativeLibraryDir, "libwhisper.so").isFile
    }
}

object SttFactory {
    fun create(context: Context): SttSession {
        val model = LocalModels(context).sttModelFile()
        return if (model != null && NativeWhisperStt.isAvailable(context)) {
            Log.i("VaaniStt", "Using packaged native STT")
            NativeWhisperStt(context, model)
        } else {
            // The development x86_64 emulator has the model files but the
            // shipped native binding is arm64-only. Its Android recognizer is
            // still a useful test path instead of failing after every hold.
            Log.i("VaaniStt", "Using Android on-device STT fallback")
            OnDeviceStt(context)
        }
    }
}
