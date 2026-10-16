//! On-demand lifecycle for the two model servers the daemon can own.
//!
//! The PRD says the key service "owns the lifecycle of every helper". The two
//! fine-tuned models are HTTP servers rather than in-process code, so owning
//! them means spawning their launcher when a run starts and killing it once
//! `idle_timeout_s` has passed with no runs. Order is the PRD's: the re-decode
//! speech server starts first, the formatter second.
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
    pub fn wait_ready(&self, timeout: Duration) -> bool {
        if self.child.is_none() {
            return port_open(self.port);
        }
        let deadline = Instant::now() + timeout;
        loop {
            if port_open(self.port) {
                return true;
            }
            if !self.running_ro() {
                return false; // launcher died: missing weights, OOM, port clash
            }
            if Instant::now() >= deadline {
                return false;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
    }

    /// `running` without `&mut` (try_wait borrows).
    fn running_ro(&self) -> bool {
        match self.child.as_ref() {
            Some(c) => std::path::Path::new(&format!("/proc/{}", c.id())).exists(),
            None => false,
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

    /// Kill and reap. Called by the idle sweep and on shutdown.
    pub fn stop(&mut self) {
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
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
}
