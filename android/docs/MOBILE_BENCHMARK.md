# Android device benchmark

The repository can compile the Android app offline, but compile time is not a
mobile performance measurement. With one authorized device connected, build
and run:

```sh
./gradlew :app:assembleDebug --offline
bash ../tools/bench_android_device.sh app/build/outputs/apk/debug/app-debug.apk
```

The harness installs the debug APK, measures launch time, and captures package
memory from `dumpsys meminfo`. It never records audio and never prints speech
or transcript text.

For the actual Flow-style gate, record these values manually for at least ten
utterances on the same device:

- speech end → final text insertion, p50 and p95;
- peak RSS during a 30-minute session;
- CPU utilization and thermal throttling;
- battery change per hour;
- recognition WER against references;
- technical-term and proper-name recall.

Do not report this gate as passed until a physical device or emulator produces
those measurements. A missing device is an unavailable measurement, not a
zero-latency result.
