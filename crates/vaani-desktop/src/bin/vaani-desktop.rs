//! Small cross-platform account/sync entry point for the desktop shell.
//! Passwords are read interactively and never accepted as command arguments.

use std::io::{self, BufRead, Write};
use std::path::PathBuf;
use vaani_core::config::Config;
use vaani_core::engine::EngineError;
use vaani_core::personalization::PersonalizationSnapshot;
use vaani_core::sync::SyncEntityKind;
use vaani_desktop::{
    DesktopSyncClient, FirebaseEmailAuth, PersonalizationRepository, SecureSessionStore,
};

#[cfg(windows)]
use vaani_core::engine::{FormatContext, LocalFormatter, NoopDenoiser};
#[cfg(windows)]
use vaani_core::vad::Vad;
#[cfg(windows)]
use vaani_desktop::platform::windows::{
    GlobalHotkey, WindowsClipboard, WindowsInserter, WindowsOverlay, WindowsSessionLoop,
    WindowsTray,
};
#[cfg(windows)]
use vaani_desktop::{AudioFrontEnd, DesktopRuntime, DesktopSession, ShortcutSpec, WorkerSttEngine};

fn env_required(name: &str) -> Result<String, EngineError> {
    std::env::var(name).map_err(|_| {
        EngineError::new(
            vaani_core::engine::EngineErrorKind::InvalidInput,
            format!("set {name} for desktop account operations"),
        )
    })
}

fn data_dir() -> Result<PathBuf, EngineError> {
    let base = if cfg!(windows) {
        std::env::var_os("LOCALAPPDATA").map(PathBuf::from)
    } else {
        std::env::var_os("XDG_DATA_HOME").map(PathBuf::from)
    }
    .or_else(|| {
        std::env::var_os("HOME").map(|home| {
            PathBuf::from(home).join(if cfg!(windows) {
                "AppData/Local"
            } else {
                ".local/share"
            })
        })
    })
    .ok_or_else(|| {
        EngineError::new(
            vaani_core::engine::EngineErrorKind::InvalidInput,
            "cannot determine desktop data directory",
        )
    })?;
    let path = base.join("vaani");
    std::fs::create_dir_all(&path).map_err(|_| {
        EngineError::new(
            vaani_core::engine::EngineErrorKind::Unavailable,
            "cannot create desktop data directory",
        )
    })?;
    Ok(path)
}

fn repository() -> Result<PersonalizationRepository, EngineError> {
    let dir = data_dir()?;
    let device_path = dir.join("device-id");
    let device_id = match std::fs::read_to_string(&device_path) {
        Ok(value) if !value.trim().is_empty() => value.trim().to_owned(),
        _ => {
            let value = uuid::Uuid::new_v4().to_string();
            std::fs::write(&device_path, &value).map_err(|_| {
                EngineError::new(
                    vaani_core::engine::EngineErrorKind::Unavailable,
                    "cannot save desktop device identity",
                )
            })?;
            value
        }
    };
    PersonalizationRepository::open(dir.join("personalization.jsonl"), device_id)
}

fn prompt(label: &str) -> io::Result<String> {
    print!("{label}: ");
    io::stdout().flush()?;
    let mut value = String::new();
    io::stdin().lock().read_line(&mut value)?;
    Ok(value.trim_end_matches(['\r', '\n']).to_owned())
}

fn print_snapshot(snapshot: PersonalizationSnapshot) {
    println!("Vocabulary ({}):", snapshot.vocabulary.len());
    for entry in snapshot.vocabulary {
        println!("  {} [{}]", entry.canonical, entry.id);
    }
    println!("Snippets ({}):", snapshot.snippets.len());
    for entry in snapshot.snippets {
        println!("  {} → {} [{}]", entry.trigger, entry.value, entry.id);
    }
    println!("Replacements ({}):", snapshot.replacements.len());
    for entry in snapshot.replacements {
        println!("  {} → {} [{}]", entry.source, entry.target, entry.id);
    }
}

fn print_settings() {
    let config = Config::load();
    println!("config: {}", Config::config_path().display());
    println!("residency: {}", config.general.residency_profile);
    println!("language: {}", config.recognition.language);
    println!("model: {}", config.recognition.model);
    println!("device: {}", config.recognition.device);
    println!("insertion: {}", config.insertion.mode);
    println!("worker_threads: {}", config.audio.worker_threads);
    println!("privacy.save_history: {}", config.privacy.save_history);
}

fn set_setting(key: &str, value: &str) -> Result<(), Box<dyn std::error::Error>> {
    let mut config = Config::load();
    let canonical = config
        .set_key(key, value)
        .map_err(|error| format!("invalid setting {key}: {error}"))?;
    config.save()?;
    println!("{key}={canonical}");
    Ok(())
}

fn command_available(name: &str) -> bool {
    let Some(path_value) = std::env::var_os("PATH") else {
        return false;
    };
    std::env::split_paths(&path_value).any(|directory| {
        let candidate = directory.join(name);
        candidate.is_file()
            || (cfg!(windows)
                && [".exe", ".cmd", ".bat"]
                    .iter()
                    .map(|suffix| directory.join(format!("{name}{suffix}")))
                    .any(|candidate| candidate.is_file()))
    })
}

fn print_doctor() {
    println!("platform: {}", std::env::consts::OS);
    println!("local personalization: ready");
    println!(
        "secure session store: {}",
        if cfg!(any(unix, windows)) {
            "available through platform keyring"
        } else {
            "unsupported on this target"
        }
    );
    if cfg!(unix) {
        let wayland = std::env::var_os("WAYLAND_DISPLAY").is_some();
        let x11 = std::env::var_os("DISPLAY").is_some();
        println!(
            "wayland insertion: {}",
            if wayland && command_available("wl-copy") && command_available("wtype") {
                "ready"
            } else if wayland {
                "needs wl-copy and wtype"
            } else {
                "not detected"
            }
        );
        println!(
            "x11 insertion: {}",
            if x11 && command_available("xclip") && command_available("xdotool") {
                "ready"
            } else if x11 {
                "needs xclip and xdotool"
            } else {
                "not detected"
            }
        );
        println!("audio/STT runtime: delegated to the Vaani daemon");
    } else if cfg!(windows) {
        println!("windows shortcut/insertion: User32 companion available");
        println!("audio/STT runtime: shell integration required");
    }
    println!("sync: optional; local mode does not require an account");
}

#[cfg(windows)]
fn run_windows_shell() -> Result<(), Box<dyn std::error::Error>> {
    let worker_path = match std::env::var_os("VAANI_WORKER") {
        Some(path) => PathBuf::from(path),
        None => std::env::current_exe()?
            .parent()
            .map(|dir| dir.join("vaani-worker.exe"))
            .ok_or("cannot determine worker location")?,
    };
    let model_path = env_required("VAANI_MODEL")?;
    let config = Config::load();
    let language = std::env::var("VAANI_LANGUAGE").unwrap_or(config.recognition.language);
    let threads = std::env::var("VAANI_THREADS")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(config.audio.worker_threads);
    let shortcut = std::env::var("VAANI_SHORTCUT")
        .map(|value| ShortcutSpec::parse(&value))
        .unwrap_or_else(|_| Ok(ShortcutSpec::default()))?;
    let hotkey = GlobalHotkey::register_spec(1, &shortcut)
        .map_err(|error| format!("could not register Vaani shortcut: {error}"))?;
    let overlay = WindowsOverlay::new()?;
    let _tray = WindowsTray::attach(&overlay, 1)?;
    let repository = repository()?;
    let runtime = DesktopRuntime::new(
        WorkerSttEngine::new(worker_path, model_path, language.clone(), threads),
        LocalFormatter,
        repository,
        overlay,
        WindowsInserter,
        WindowsClipboard,
    );
    let session = DesktopSession::new(runtime, AudioFrontEnd::new(Vad::default(), NoopDenoiser));
    let context = FormatContext {
        application: None,
        language,
        personalization: PersonalizationSnapshot::default(),
    };
    let shell = WindowsSessionLoop::new(hotkey, session, context);
    shell.run(|result| match result {
        Ok(Some(_report)) => eprintln!("Vaani session delivered"),
        Ok(None) => eprintln!("Vaani session contained no speech"),
        Err(error) => eprintln!("Vaani session failed: {error}"),
    })?;
    Ok(())
}

fn personalization_menu(
    repository: &PersonalizationRepository,
) -> Result<(), Box<dyn std::error::Error>> {
    loop {
        println!("\nVaani local personalization");
        println!("  list · add-vocabulary · add-snippet · add-replacement · remove · quit");
        match prompt("Action")?.trim().to_ascii_lowercase().as_str() {
            "list" => print_snapshot(repository.snapshot()?),
            "add-vocabulary" => {
                let canonical = prompt("Canonical term")?;
                let aliases = prompt("Spoken aliases (comma-separated)")?
                    .split(',')
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_owned)
                    .collect();
                let category = prompt("Category (optional)")?;
                repository.add_vocabulary(
                    canonical,
                    aliases,
                    (!category.is_empty()).then_some(category),
                )?;
                println!("Vocabulary saved locally.");
            }
            "add-snippet" => {
                let trigger = prompt("Snippet trigger")?;
                let value = prompt("Snippet expansion")?;
                repository.add_snippet(trigger, value)?;
                println!("Snippet saved locally.");
            }
            "add-replacement" => {
                let source = prompt("Replacement source")?;
                let target = prompt("Replacement target")?;
                repository.add_replacement(source, target)?;
                println!("Replacement saved locally.");
            }
            "remove" => {
                let kind = match prompt("Kind (vocabulary|snippet|replacement)")?
                    .to_ascii_lowercase()
                    .as_str()
                {
                    "vocabulary" => SyncEntityKind::Vocabulary,
                    "snippet" => SyncEntityKind::Snippet,
                    "replacement" => SyncEntityKind::Replacement,
                    _ => {
                        println!("Unknown kind.");
                        continue;
                    }
                };
                let id = prompt("Record id")?;
                repository.remove_current(kind, &id)?;
                println!("Record removed locally.");
            }
            "quit" | "q" | "" => break,
            _ => println!("Choose one of the listed actions."),
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let default_command = if cfg!(windows) { "run" } else { "status" };
    let command = std::env::args()
        .nth(1)
        .unwrap_or_else(|| default_command.into());
    match command.as_str() {
        "run" => {
            #[cfg(windows)]
            run_windows_shell()?;
            #[cfg(not(windows))]
            return Err("the desktop shell run command is only available on Windows".into());
        }
        "settings" => print_settings(),
        "config-get" => println!("{}", toml::to_string_pretty(&Config::load())?),
        "config-set" => {
            let key = std::env::args().nth(2).ok_or("config-set requires a key")?;
            let value = std::env::args().nth(3).ok_or("config-set requires a value")?;
            set_setting(&key, &value)?;
        }
        "login" => {
            let project = env_required("VAANI_FIREBASE_PROJECT")?;
            let api_key = env_required("VAANI_FIREBASE_API_KEY")?;
            let store = SecureSessionStore::new(&project, &api_key);
            let mut email = String::new();
            print!("Email: ");
            io::stdout().flush()?;
            io::stdin().lock().read_line(&mut email)?;
            let password = rpassword::prompt_password("Password: ")?;
            let session = FirebaseEmailAuth::new(api_key).sign_in(email.trim(), &password)?;
            store.save(&session)?;
            println!("signed in");
        }
        "sync" => {
            let project = env_required("VAANI_FIREBASE_PROJECT")?;
            let api_key = env_required("VAANI_FIREBASE_API_KEY")?;
            let store = SecureSessionStore::new(&project, &api_key);
            let repository = repository()?;
            let mut client = DesktopSyncClient::new(project, repository);
            if !client.restore_session(&store)? {
                return Err("not signed in; run `vaani-desktop login` first".into());
            }
            let cycle = client.sync_once()?;
            println!("synced: pushed {}, pulled {}", cycle.pushed, cycle.pulled);
        }
        "sign-out" => {
            let project = env_required("VAANI_FIREBASE_PROJECT")?;
            let api_key = env_required("VAANI_FIREBASE_API_KEY")?;
            let store = SecureSessionStore::new(&project, &api_key);
            store.clear()?;
            println!("signed out");
        }
        "status" => {
            let repository = repository()?;
            let snapshot = repository.snapshot()?;
            let account = match (
                std::env::var("VAANI_FIREBASE_PROJECT"),
                std::env::var("VAANI_FIREBASE_API_KEY"),
            ) {
                (Ok(project), Ok(api_key)) => {
                    let store = SecureSessionStore::new(project, api_key);
                    match store.load() {
                        Ok(Some(_)) => "signed in",
                        Ok(None) => "local only",
                        Err(_) => "secure store unavailable",
                    }
                }
                _ => "local only",
            };
            println!(
                "local: vocabulary {}, snippets {}, replacements {}; account: {}",
                snapshot.vocabulary.len(),
                snapshot.snippets.len(),
                snapshot.replacements.len(),
                account
            );
        }
        "doctor" => print_doctor(),
        "personalize" => personalization_menu(&repository()?)?,
        _ => {
            return Err(
                "usage: vaani-desktop [run|settings|config-get|config-set KEY VALUE|login|sync|sign-out|status|doctor|personalize]".into(),
            )
        }
    }
    Ok(())
}
