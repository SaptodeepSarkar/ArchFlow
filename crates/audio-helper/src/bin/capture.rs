//! Manual self-check binary used by TESTS/gates/gate-04.sh.
//! Records --secs seconds, prints flag transitions and capture stats.

use audio_helper::Recorder;
use std::time::{Duration, Instant};

fn main() {
    let secs: u64 = std::env::args()
        .skip_while(|a| a != "--secs")
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(5);

    let mut rec = Recorder::new();
    if let Err(e) = rec.start() {
        println!("start_failed error={e}");
        std::process::exit(1);
    }
    println!("during busy={} killable={}", rec.is_busy(), rec.is_killable());
    if !rec.is_busy() || rec.is_killable() {
        println!("flags_wrong_during_recording");
        std::process::exit(1);
    }

    let t = Instant::now();
    std::thread::sleep(Duration::from_secs(secs));
    let wall = t.elapsed().as_secs_f64();

    match rec.stop() {
        Ok(cap) => {
            println!(
                "after busy={} killable={}",
                rec.is_busy(),
                rec.is_killable()
            );
            let rms = (cap.samples.iter().map(|&s| (s as f64).powi(2)).sum::<f64>()
                / cap.samples.len().max(1) as f64)
                .sqrt();
            println!(
                "capture samples={} secs={:.2} wall={:.2} rms={:.1}",
                cap.samples.len(),
                cap.secs(),
                wall,
                rms
            );
            if rec.is_busy() || !rec.is_killable() {
                println!("flags_wrong_after_stop");
                std::process::exit(1);
            }
        }
        Err(e) => {
            println!("stop_failed error={e}");
            std::process::exit(1);
        }
    }
}
