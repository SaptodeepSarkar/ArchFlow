//! Small cross-platform account/sync entry point for the desktop shell.
//! Passwords are read interactively and never accepted as command arguments.

use std::io::{self, BufRead, Write};
use std::path::PathBuf;
use vaani_core::engine::EngineError;
use vaani_core::personalization::PersonalizationSnapshot;
use vaani_core::sync::SyncEntityKind;
use vaani_desktop::{
    DesktopSyncClient, FirebaseEmailAuth, PersonalizationRepository, SecureSessionStore,
};

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
    let command = std::env::args().nth(1).unwrap_or_else(|| "status".into());
    match command.as_str() {
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
        "personalize" => personalization_menu(&repository()?)?,
        _ => return Err("usage: vaani-desktop [login|sync|sign-out|status|personalize]".into()),
    }
    Ok(())
}
