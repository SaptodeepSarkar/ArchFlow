use crate::{
    add_page, button, column, label, task,
    ui_components::{actions, card, mark},
    Update,
};
use adw::prelude::*;
use gtk::Orientation;
use vaani_core::protocol::RequestKind;
use vaani_local::{ipc, settings};

pub fn build(stack: &gtk::Stack, tx: &async_channel::Sender<Update>) {
    let home = column();
    let cfg = settings::read(&vaani_core::config::Config::config_path())
        .ok()
        .map(|(_, cfg)| cfg);
    let hero = card("VOICE, WITHOUT THE FRICTION", "", "hero");
    let heading = gtk::Box::new(Orientation::Horizontal, 24);
    let title = label("Speak.\nVaani writes.");
    title.add_css_class("hero-title");
    title.set_hexpand(true);
    heading.append(&title);
    heading.append(&mark(78));
    hero.append(&heading);
    hero.append(&label(
        "Start a dictation, say what’s on your mind, and keep writing.",
    ));
    let row = actions(&hero);
    let dictate = button("Start / finish dictation", &row);
    dictate.add_css_class("suggested-action");
    connect(&dictate, tx, RequestKind::Toggle);
    let cancel = button("Cancel", &row);
    connect(&cancel, tx, RequestKind::Cancel);
    home.append(&hero);

    let metrics = gtk::Box::new(Orientation::Horizontal, 14);
    metrics.set_homogeneous(true);
    for (title, value, hint) in [
        (
            "Your shortcut",
            cfg.as_ref()
                .map(|c| c.general.shortcut.as_str())
                .unwrap_or("Not configured"),
            "Change your shortcut through the desktop setup helper.",
        ),
        (
            "Speech model",
            cfg.as_ref()
                .map(|c| c.recognition.model.as_str())
                .unwrap_or("Not configured"),
            "Choose a model in Settings. Install one on Models.",
        ),
    ] {
        let metric = card(title, "", "");
        let value = label(value);
        value.add_css_class("metric-value");
        metric.append(&value);
        let hint = label(hint);
        hint.add_css_class("muted");
        metric.append(&hint);
        metrics.append(&metric);
    }
    home.append(&metrics);
    let service = card("Your dictation controls", "Start the shortcut service when you need it. Models load on demand; Economy releases them after use.", "");
    let row = actions(&service);
    for (text, command) in [("Start service", "start"), ("Stop service", "stop")] {
        let b = button(text, &row);
        let t = tx.clone();
        b.connect_clicked(move |_| {
            task(t.clone(), move || {
                anyhow::ensure!(
                    std::process::Command::new("systemctl")
                        .args(["--user", command, "vaanid.service"])
                        .status()?
                        .success(),
                    "Service action failed. Check your user session."
                );
                Ok(Update::Status(format!("Service {command} requested")))
            })
        });
    }
    let row = actions(&service);
    let copy = button("Copy pending text", &row);
    connect(&copy, tx, RequestKind::CopyPending);
    let mic = button("Test microphone", &row);
    connect(&mic, tx, RequestKind::MicTest { secs: 3 });
    let doctor = button("Check setup", &row);
    connect(&doctor, tx, RequestKind::Doctor);
    home.append(&service);
    let words = card("Personal vocabulary", "Names, places and technical terms belong here. Add them on Personalize, then bring them to your other device with local pairing.", "sky");
    let vocabulary = button("Open Personalize", &words);
    let target = stack.clone();
    vocabulary.connect_clicked(move |_| target.set_visible_child_name("personal"));
    home.append(&words);
    add_page(stack, &home, "home", "Home");
}
fn connect(button: &gtk::Button, tx: &async_channel::Sender<Update>, kind: RequestKind) {
    let tx = tx.clone();
    button.connect_clicked(move |_| {
        let kind = kind.clone();
        task(tx.clone(), move || {
            let response = ipc::request(kind)?;
            let message = if let Some(data) = response.data {
                if let Some(checks) = data["checks"].as_object() {
                    let missing: Vec<_> = checks
                        .iter()
                        .filter(|(_, v)| v.as_bool() == Some(false))
                        .map(|(k, _)| k.as_str())
                        .collect();
                    if missing.is_empty() {
                        "Setup checks completed. Review installed models in Models.".into()
                    } else {
                        format!("Unavailable setup components: {}", missing.join(", "))
                    }
                } else if data["rms"].is_number() {
                    format!(
                        "Microphone test: level {:.3}. Speak normally and check your input volume.",
                        data["rms"].as_f64().unwrap_or_default()
                    )
                } else {
                    response
                        .message
                        .unwrap_or_else(|| "Request completed".into())
                }
            } else {
                response
                    .message
                    .unwrap_or_else(|| "Dictation request sent".into())
            };
            Ok(Update::Status(message))
        });
    });
}
