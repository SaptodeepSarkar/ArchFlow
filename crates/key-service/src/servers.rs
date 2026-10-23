//! On-demand lifecycle for the two model servers the daemon can own.
//!
//! The PRD says the key service "owns the lifecycle of every helper". The two
//! fine-tuned models are HTTP servers rather than in-process code, so owning
//! them means spawning their launcher when a run starts and killing it once
//! `idle_timeout_s` has passed with no runs. Order is the PRD's: the re-decode
//! speech server starts first, the formatter second, and each start unloads the
//! other side first -- the two models are never in VRAM at once.
//!
//! Opt-in per server. `VAANI_STT_REFINE_SERVER` and `VAANI_LLM_SERVER` point at
//! the launcher scripts; with either unset the daemon owns nothing for it and
//! behaves exactly as before (externally started server, or the existing
//! fallbacks: streaming words, the rule engine). A port that already answers is
//! left alone, so a hand-started server is never fought over.
//!
//! Spawning never blocks a run. `wait_ready` is bounded and only ever bites on
//! the first run after the idle window closed, because both servers bind their
//! port only once the weights are in memory -- an open port means a warm model.

use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use crate::timeouts;

/// A cold server's budget before the caller falls back to what it already has.
/// Generous on purpose: the re-decode server loads an 809M model, and a warm
/// one answers this instantly.
/// shortcut: one fixed budget rather than a setting, revisit if a bigger model
/// is served.
pub const READY_TIMEOUT: Duration = Duration::from_secs(25);

/// How long a stopped server gets to exit on SIGTERM before SIGKILL.
/// shortcut: one fixed grace, revisit if a server needs longer to release VRAM.
const STOP_GRACE: Duration = Duration::from_millis(500);
const SIGTERM: i32 = 15;

extern "C" {
    fn kill(pid: i32, sig: i32) -> i32;
}

/// One server the daemon owns. `name` matches the PRD's helper names, so the
/// offload log lines read like the rest of the lifecycle.
pub struct Server {
    pub name: &'static str,
    launcher: PathBuf,
    port: u16,
    child: Option<Child>,
    last_used_s: u64,
}

impl Server {
    pub fn new(name: &'static str, launcher: PathBuf, port: u16) -> Self {
        Self {
            name,
            launcher,
            port,
            child: None,
            last_used_s: 0,
        }
    }

    /// The servers this daemon owns, in start order (speech, then formatter).
    /// A launcher that is not configured or not on disk is simply not owned.
    pub fn owned() -> Vec<Server> {
        let mut v = Vec::new();
        if let Some(s) = from_env(
            "stt",
            "VAANI_STT_REFINE_SERVER",
            "VAANI_STT_REFINE_ENDPOINT",
            8083,
        ) {
            v.push(s);
        }
        if let Some(s) = from_env("llm", "VAANI_LLM_SERVER", "VAANI_LLM_ENDPOINT", 8081) {
            v.push(s);
        }
        v
    }

    /// Spawn the launcher unless it is already running or something else is
    /// already serving that port. Marks the server as used.
    pub fn start(&mut self, now_s: u64) {
        self.last_used_s = now_s;
        if self.running() {
            return;
        }
        if port_open(self.port) {
            // Not ours: an externally started server (or a stale one) answers
            // there already, and killing it is not this daemon's business.
            crate::log(
                "spawn",
                &format!(
                    "{} server already serving on port {}, not spawning",
                    self.name, self.port
                ),
            );
            return;
        }
        let mut cmd = Command::new("bash");
        cmd.arg(&self.launcher)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            // stderr is inherited: a failed bind or a CUDA OOM must be visible
            // in `journalctl --user -u vaani-key.service`.
            .stderr(Stdio::inherit());
        // Each launcher takes its port its own way: serve-formatter.sh reads
        // VAANI_LLM_PORT, serve-refine-stt.sh forwards its extra args to the
        // python server. Either way the child binds exactly the port the daemon
        // calls, which is what makes "owned" mean anything.
        match self.name {
            "stt" => {
                cmd.arg("--port").arg(self.port.to_string());
            }
            _ => {
                cmd.env("VAANI_LLM_PORT", self.port.to_string());
            }
        }
        match cmd.spawn() {
            Ok(c) => {
                self.child = Some(c);
                crate::log(
                    "spawn",
                    &format!(
                        "started {} server ({}) on port {}",
                        self.name,
                        self.launcher.display(),
                        self.port
                    ),
                );
            }
            Err(e) => crate::log(
                "error",
                &format!(
                    "could not start {} server ({}): {e}",
                    self.name,
                    self.launcher.display()
                ),
            ),
        }
    }

    /// True while the launcher process we spawned is alive. A launcher that has
    /// exited is reaped and forgotten here, so the periodic sweep can never
    /// leave a zombie behind.
    pub fn running(&mut self) -> bool {
        let exited = match self.child.as_mut() {
            Some(c) => matches!(c.try_wait(), Ok(Some(_))),
            None => return false,
        };
        if exited {
            self.child = None;
        }
        !exited
    }

    /// Bounded wait for the port to answer. Only the server we own is waited
    /// for: one we do not own either answers already or never will.
    pub fn wait_ready(&mut self, timeout: Duration) -> bool {
        if self.child.is_none() {
            return port_open(self.port);
        }
        let deadline = Instant::now() + timeout;
        loop {
            if health_ok(self.port) {
                return true;
            }
            // `running` reaps an exited launcher; a zombie in /proc must not
            // make this wait the full timeout.
            if !self.running() {
                return false; // launcher died: missing weights, OOM, port clash
            }
            if Instant::now() >= deadline {
                return false;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
    }

    /// Mark the server as used now, which restarts its idle window.
    pub fn touch(&mut self, now_s: u64) {
        self.last_used_s = now_s;
    }

    /// This server as the idle sweep sees it, for `timeouts::due_for_offload`.
    /// A spawned server is never "busy": it serves requests one at a time and
    /// the sweep only runs while no pipeline is active.
    pub fn helper(&self) -> timeouts::Helper {
        timeouts::Helper {
            name: self.name.to_string(),
            last_activity_s: self.last_used_s,
            busy: false,
            killable: true,
        }
    }

    /// True when something outside this daemon answers on our port, so `start`
    /// deliberately did not spawn. Test surface for the gate's "already
    /// serving" case.
    pub fn externally_served(&self) -> bool {
        self.child.is_none() && port_open(self.port)
    }

    /// Stop and reap, waiting for the exit: that wait is what lets a caller
    /// start the other model knowing this one's VRAM is gone. SIGTERM first so
    /// the server can shut down cleanly; SIGKILL if it outlasts the grace.
    pub fn stop(&mut self) {
        let Some(mut c) = self.child.take() else { return };
        // SAFETY: libc kill on the pid of a child this process owns; no memory
        // is involved.
        unsafe {
            kill(c.id() as i32, SIGTERM);
        }
        let deadline = Instant::now() + STOP_GRACE;
        while Instant::now() < deadline {
            if matches!(c.try_wait(), Ok(Some(_))) {
                return;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        let _ = c.kill();
        let _ = c.wait();
    }
}

/// Stop one owned server before the other model loads. `stop` waits, so when
/// this returns the VRAM is back. A server this daemon did not spawn is left
/// alone (that is the external-server rule).
fn unload(fleet: &mut [Server], name: &str) {
    if let Some(s) = fleet.iter_mut().find(|s| s.name == name) {
        if s.running() {
            s.stop();
            crate::log(
                "offload",
                &format!("{name} server stopped: one model in VRAM at a time"),
            );
        }
    }
}

/// A run begins with the speech server. A formatter still warm from the last
/// run is unloaded first: the two models are never resident together.
pub fn start_stt(fleet: &mut [Server], now_s: u64) {
    unload(fleet, "llm");
    if let Some(s) = fleet.iter_mut().find(|s| s.name == "stt") {
        s.start(now_s);
    }
}

/// A run ends with the formatter warm and nothing left to ask it. Stop it now
/// rather than on the next trigger, whose path must not carry its shutdown.
/// `start_stt`'s unload stays as the safety net.
pub fn park_formatter(fleet: &mut [Server]) {
    unload(fleet, "llm");
}

/// The PRD handoff: the speech server is stopped (and confirmed gone) before
/// the formatter is spawned. Returns true when the formatter is usable: not
/// owned, or answering on its port.
pub fn handoff_to_llm(fleet: &mut [Server], now_s: u64, ready: Duration) -> bool {
    unload(fleet, "stt");
    match fleet.iter_mut().find(|s| s.name == "llm") {
        Some(s) => {
            s.start(now_s);
            s.wait_ready(ready)
        }
        None => true,
    }
}

fn from_env(name: &'static str, server_var: &str, endpoint_var: &str, default_port: u16) -> Option<Server> {
    let server = std::env::var(server_var).ok()?;
    let path = PathBuf::from(&server);
    if !path.is_file() {
        eprintln!("vaani key-service: {server_var}={server} is not a file, not owning that server");
        return None;
    }
    // The port comes from the endpoint the client will actually call, so the
    // child is told to bind the same one.
    let endpoint = std::env::var(endpoint_var).unwrap_or_default();
    Some(Server::new(name, path, port_of(&endpoint).unwrap_or(default_port)))
}

/// Port from an endpoint like `http://127.0.0.1:8083`, `127.0.0.1:8083`, or a
/// bare port. `None` when the string carries no usable port.
fn port_of(endpoint: &str) -> Option<u16> {
    let tail = endpoint.rsplit(':').next()?;
    // Trailing digits only: a scheme or a path leaves nothing to parse.
    let digits: String = tail.chars().take_while(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return None;
    }
    digits.parse::<u16>().ok().filter(|p| *p > 0)
}

fn port_open(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&addr, Duration::from_millis(150)).is_ok()
}

/// Ready means the HTTP surface says 200. llama-server binds its port and
/// answers 503 while the weights load, so a bare TCP connect counted a loading
/// formatter as ready, the run got an empty reply, and formatting fell back to
/// the rule engine.
fn health_ok(port: u16) -> bool {
    use std::io::{Read, Write};
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(150)) else {
        return false;
    };
    let _ = s.set_read_timeout(Some(Duration::from_millis(500)));
    let req = format!("GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    if s.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 32];
    let n = s.read(&mut buf).unwrap_or(0);
    String::from_utf8_lossy(&buf[..n]).starts_with("HTTP/1.1 200")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn port_parses_from_endpoints_and_bare_values() {
        assert_eq!(port_of("http://127.0.0.1:8083"), Some(8083));
        assert_eq!(port_of("127.0.0.1:8082"), Some(8082));
        assert_eq!(port_of("8081"), Some(8081));
        assert_eq!(port_of("http://127.0.0.1"), None);
        assert_eq!(port_of(""), None);
        assert_eq!(port_of("http://host:notaport"), None);
        assert_eq!(port_of("http://host:0"), None);
    }

    /// A dead launcher is not "running", so the sweep never sees it and
    /// `wait_ready` stops waiting for it instead of sitting out the budget.
    #[test]
    fn a_finished_launcher_is_reaped_and_not_running() {
        let mut s = Server::new("llm", PathBuf::from("/nonexistent"), 65001);
        s.child = Some(Command::new("true").spawn().expect("spawn true"));
        std::thread::sleep(Duration::from_millis(200));
        assert!(!s.running(), "exited launcher is not running");
        assert!(s.child.is_none(), "and it is reaped, not left as a zombie");
        let t0 = Instant::now();
        assert!(!s.wait_ready(Duration::from_secs(5)));
        assert!(
            t0.elapsed() < Duration::from_secs(2),
            "a dead launcher must not burn the whole readiness budget"
        );
    }

    /// A bound port that is still loading (llama-server answers 503) is not
    /// ready; a bare TCP connect used to count it as ready.
    #[test]
    fn a_bound_port_answering_503_is_not_ready() {
        let l = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = l.local_addr().expect("addr").port();
        std::thread::spawn(move || {
            use std::io::Write;
            if let Ok((mut s, _)) = l.accept() {
                let _ = s.write_all(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n");
            }
        });
        let mut srv = Server::new("llm", PathBuf::from("/nonexistent"), port);
        srv.child = Some(Command::new("sleep").arg("5").spawn().expect("spawn sleep"));
        assert!(!srv.wait_ready(Duration::from_millis(300)));
        srv.stop();
    }

    #[test]
    fn wait_ready_does_not_burn_the_budget_on_a_zombie() {
        let mut s = Server::new("llm", PathBuf::from("/nonexistent"), 65002);
        s.child = Some(Command::new("true").spawn().expect("spawn true"));
        std::thread::sleep(Duration::from_millis(200));
        let t0 = Instant::now();
        assert!(!s.wait_ready(Duration::from_secs(5)));
        assert!(t0.elapsed() < Duration::from_secs(2));
    }

    /// The idle window itself is `timeouts::decide`'s; what this module owns is
    /// reporting each server's last use into that decision.
    #[test]
    fn helper_reports_last_use_for_the_sweep() {
        let mut s = Server::new("stt", PathBuf::from("/nonexistent"), 65000);
        s.touch(100);
        assert_eq!(s.helper().last_activity_s, 100);
        assert_eq!(s.helper().name, "stt");
        assert!(!s.helper().busy);
        assert!(s.helper().killable);
    }

    /// Stopping waits for the process: the caller starts the other model right
    /// after this returns, so the VRAM must already be released.
    #[test]
    fn stop_waits_for_the_server_to_exit() {
        let mut s = Server::new("llm", PathBuf::from("/nonexistent"), 65003);
        s.child = Some(Command::new("sleep").arg("300").spawn().expect("spawn sleep"));
        assert!(s.running());
        let t0 = Instant::now();
        s.stop();
        assert!(!s.running());
        assert!(s.child.is_none());
        assert!(
            t0.elapsed() < Duration::from_secs(2),
            "a server that honours SIGTERM is reaped at once, not after the grace"
        );
    }
}
