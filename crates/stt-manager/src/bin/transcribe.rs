//! Manual self-check binary used by TESTS/gates/gate-05.sh.
//! Transcribes one --wav, streaming words as they decode, then prints stats.

use stt_manager::{pick_device, resolve_model, resolve_python};

fn main() {
    let wav = std::env::args()
        .skip_while(|a| a != "--wav")
        .nth(1)
        .unwrap_or_else(|| {
            eprintln!("usage: transcribe --wav PATH");
            std::process::exit(2);
        });

    let device = pick_device();
    let python = resolve_python().unwrap_or_else(|| {
        eprintln!("no python with vosk found (tried VAANI_STT_PYTHON, Kyuma venv, python3)");
        std::process::exit(1);
    });
    let model = resolve_model().unwrap_or_else(|| {
        eprintln!("no STT model dir found");
        std::process::exit(1);
    });
    println!("device={device:?} python={python} model={model}");

    let mut busy_seen = false;
    let mut s = stt_manager::Session::start(&wav, &python, &model).unwrap_or_else(|e| {
        eprintln!("start_failed error={e}");
        std::process::exit(1);
    });
    if s.is_busy() {
        busy_seen = true;
    }
    println!("during busy={} killable={}", s.is_busy(), s.is_killable());
    let mut n = 0;
    while let Some(w) = s.next_word() {
        n += 1;
        println!("word t={:.2} text={}", w.t, w.text);
    }
    match s.finish() {
        Ok(st) => {
            println!("after busy={} killable={}", s.is_busy(), s.is_killable());
            println!(
                "result words={} streamed={} audio={:.2} infer={:.2} rtf={:.3}",
                st.words,
                n,
                st.audio_secs,
                st.infer_secs,
                st.rtf()
            );
            if st.words == 0 {
                eprintln!("no_words_decoded");
                std::process::exit(1);
            }
            if !(s.is_killable() && busy_seen) {
                eprintln!("flags_wrong");
                std::process::exit(1);
            }
        }
        Err(e) => {
            eprintln!("transcribe_failed error={e}");
            std::process::exit(1);
        }
    }
}
