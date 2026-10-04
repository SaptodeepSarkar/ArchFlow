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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
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
import java.util.concurrent.atomic.AtomicReference
import kotlin.coroutines.coroutineContext

data class SttSegmentEvidence(val segmentId: Int, val startMs: Long, val endMs: Long, val text: String)
data class SttFinalEvidence(val text: String, val backend: String,
                          val segments: List<SttSegmentEvidence> = emptyList())

/** Retained for the final-evidence contract; services use DictationSessionGate. */
internal class SttSessionFence {
    private var generation = 0L
    @Synchronized fun begin(): Long = ++generation
    @Synchronized fun invalidate(): Long = ++generation
    @Synchronized fun isCurrent(candidate: Long): Boolean = candidate == generation
}

interface SttSession {
    fun start(onReady: () -> Unit, onResult: (SttFinalEvidence) -> Unit, onError: (String) -> Unit, onRms: (Float) -> Unit = {})
    fun stop()
    fun cancel()
}

/** Android's installed on-device recognizer is the usable no-network STT baseline. */
class OnDeviceStt(private val context: Context) : SttSession {
    private var recognizer: SpeechRecognizer? = null
    private val sessions = DictationSessionGate()

    override fun start(onReady: () -> Unit, onResult: (SttFinalEvidence) -> Unit, onError: (String) -> Unit, onRms: (Float) -> Unit) {
        if (context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            onError("Microphone permission is not granted")
            return
        }
        if (!SpeechRecognizer.isOnDeviceRecognitionAvailable(context)) {
            onError("On-device speech is unavailable. Install an offline speech service first.")
            return
        }
        cancel()
        val token = sessions.begin()
        val speech = SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        recognizer = speech
        speech.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) { if (sessions.isListening(token)) onReady() }
            override fun onResults(results: Bundle) {
                if (sessions.acceptResult(token)) {
                    releaseRecognizer()
                    onResult(SttFinalEvidence(
                        results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty(),
                        "android-on-device"))
                }
            }
            override fun onError(error: Int) {
                if (sessions.acceptResult(token)) {
                    releaseRecognizer()
                    onError("Speech recognition error ($error)")
                }
            }
            override fun onBeginningOfSpeech() = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit
            override fun onPartialResults(partialResults: Bundle?) = Unit
            override fun onRmsChanged(rmsdB: Float) {
                if (sessions.isListening(token)) onRms(((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
            }
        })
        speech.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
        })
    }

    override fun stop() = recognizer?.stopListening() ?: Unit
    override fun cancel() { sessions.invalidate(); releaseRecognizer() }

    private fun releaseRecognizer() {
        val owned = recognizer ?: return
        recognizer = null
        try { owned.cancel() } finally { owned.destroy() }
    }
}

/** File-backed whisper.cpp session used when a user-installed model pack exists. */
class NativeWhisperStt(
    private val context: Context,
    private val modelFile: File,
    private val language: String = OnboardingState.writingLanguage(context),
) : SttSession {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val recorder = AtomicReference<OwnedResource<AudioRecord>?>(null)
    @Volatile private var recording = false
    private var job: Job? = null

    override fun start(onReady: () -> Unit, onResult: (SttFinalEvidence) -> Unit, onError: (String) -> Unit, onRms: (Float) -> Unit) {
        if (context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            onError("Microphone permission is not granted")
            return
        }
        if (!modelFile.isFile) { onError("Embedded STT model is missing"); return }
        val minimum = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, ENCODING)
        if (minimum <= 0) { onError("Audio input is unavailable"); return }
        recording = true
        job = scope.launch {
            var owned: OwnedResource<AudioRecord>? = null
            try {
                coroutineContext.ensureActive()
                val audio = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE, CHANNEL_CONFIG, ENCODING, minimum * 2)
                owned = OwnedResource(audio) { input ->
                    try { input.runCatching { stop() } } finally { input.release() }
                }
                recorder.set(owned)
                coroutineContext.ensureActive()
                check(audio.state == AudioRecord.STATE_INITIALIZED)
                if (!recording) return@launch
                owned.useIfOpen { it.startRecording() }
                withContext(Dispatchers.Main) { onReady() }
                val pcm = ByteArrayOutputStream()
                val buffer = ByteArray(minimum)
                val started = android.os.SystemClock.elapsedRealtime()
                var lastRms = 0L
                while (recording && android.os.SystemClock.elapsedRealtime() - started < MAX_RECORDING_MS) {
                    coroutineContext.ensureActive()
                    // Nonblocking read keeps close/cancel from waiting for a microphone read.
                    val read = owned.useIfOpen { it.read(buffer, 0, buffer.size, AudioRecord.READ_NON_BLOCKING) } ?: break
                    check(read >= 0) { "Audio read failed" }
                    if (read > 0) {
                        pcm.write(buffer, 0, read)
                        val now = android.os.SystemClock.elapsedRealtime()
                        if (now - lastRms >= 50L) {
                            lastRms = now
                            val level = rmsLevel(buffer, read)
                            withContext(Dispatchers.Main) { onRms(level) }
                        }
                    }
                    delay(10)
                }
                owned.close()
                recorder.compareAndSet(owned, null)
                coroutineContext.ensureActive()
                if (pcm.size() < MIN_AUDIO_BYTES) {
                    withContext(Dispatchers.Main) { onError("No speech detected") }
                    return@launch
                }
                val wav = File.createTempFile("vaani-stt-", ".wav", context.cacheDir)
                try {
                    writeWav(wav, pcm.toByteArray())
                    coroutineContext.ensureActive()
                    ModelLifecycle.stt.use(ModelLifecycle.identity(modelFile), ModelLifecycle.ttl(context),
                        load = { Whisper.loadModel(context, modelFile.absolutePath) }) { model ->
                        coroutineContext.ensureActive()
                        val result = Whisper.transcribe(model, wav.absolutePath, WhisperConfig(language = language, threads = 2))
                        coroutineContext.ensureActive()
                        val segments = result.segments.mapIndexed { index, segment ->
                            SttSegmentEvidence(index, segment.startMs, segment.endMs, segment.text)
                        }
                        withContext(Dispatchers.Main) {
                            onResult(SttFinalEvidence(result.text.trim(), "whisper.cpp", segments))
                        }
                    }
                } finally { wav.delete() }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                coroutineContext.ensureActive()
                Log.w("VaaniStt", "Native STT session failed: ${error.javaClass.simpleName}")
                withContext(Dispatchers.Main) { onError("Embedded STT failed") }
            } finally {
                owned?.close()
                recorder.compareAndSet(owned, null)
                recording = false
            }
        }
    }

    override fun stop() { recording = false }

    override fun cancel() {
        recording = false
        job?.cancel()
        scope.cancel()
        recorder.getAndSet(null)?.close()
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
