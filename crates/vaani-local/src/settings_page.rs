use crate::{add_page, button, column, entry, label, task, Update};
use adw::prelude::*;
use std::{cell::RefCell, rc::Rc};
use vaani_core::protocol::RequestKind;
use vaani_local::{ipc, settings};
pub fn build(stack: &gtk::Stack, status: &gtk::Label, tx: &async_channel::Sender<Update>) {
    let prefs = column();
    prefs.append(&label("Settings are loaded from your existing file. Saving validates values and preserves comments and unknown fields."));
    let language = gtk::DropDown::from_strings(&["en", "hi", "bn"]);
    prefs.append(&label("Writing language"));
    prefs.append(&language);
    let profile = gtk::DropDown::from_strings(&["economy", "balanced", "ready"]);
    prefs.append(&label("Model retention"));
    prefs.append(&profile);
    let retention = gtk::SpinButton::with_range(1.0, 120.0, 1.0);
    prefs.append(&label(
        "Idle retention in seconds (Economy always unloads immediately)",
    ));
    prefs.append(&retention);
    let delivery = gtk::DropDown::from_strings(&["automatic", "copy-only", "review"]);
    prefs.append(&label("Text delivery"));
    prefs.append(&delivery);
    let stt_model =
        gtk::DropDown::from_strings(&["tiny", "base", "base.en", "small", "cozy", "v5"]);
    prefs.append(&label("Installed speech model"));
    prefs.append(&stt_model);
    let formatter_path = entry("Optional formatter model path", &prefs);
    let loaded = Rc::new(RefCell::new(None::<String>));
    let path = vaani_core::config::Config::config_path();
    let load = button("Reload settings", &prefs);
    let load_fields = {
        let loaded = loaded.clone();
        let language = language.clone();
        let profile = profile.clone();
        let retention = retention.clone();
        let delivery = delivery.clone();
        let stt_model = stt_model.clone();
        let formatter_path = formatter_path.clone();
        let status = status.clone();
        let path = path.clone();
        move || {
            match settings::read(&path){Ok((text,cfg))=>{language.set_selected(["en","hi","bn"].iter().position(|v|*v==cfg.recognition.language).unwrap_or(0) as u32);profile.set_selected(["economy","balanced","ready"].iter().position(|v|*v==cfg.general.residency_profile).unwrap_or(0) as u32);retention.set_value(cfg.recognition.server_idle_secs.clamp(1,120) as f64);delivery.set_selected(["automatic","copy-only","review"].iter().position(|v|*v==cfg.insertion.mode).unwrap_or(0) as u32);stt_model.set_selected(["tiny","base","base.en","small","cozy","v5"].iter().position(|v|*v==cfg.recognition.model).unwrap_or(1) as u32);formatter_path.set_text(&cfg.cleanup.model_path);*loaded.borrow_mut()=Some(text);status.set_text("Settings loaded");},Err(_)=>status.set_text("Settings missing or malformed. Preserve the file; install/start Vaani or repair it before saving.")}
        }
    };
    load_fields();
    load.connect_clicked(move |_| load_fields());
    let save = button("Save settings", &prefs);
    let t = tx.clone();
    save.connect_clicked(move |_| {
        let Some(expected) = loaded.borrow().clone() else {
            return;
        };
        let updates = vec![
            (
                "recognition.model",
                ["tiny", "base", "base.en", "small", "cozy", "v5"][stt_model.selected() as usize]
                    .to_string(),
            ),
            ("cleanup.model_path", formatter_path.text().to_string()),
            (
                "recognition.language",
                ["en", "hi", "bn"][language.selected() as usize].to_string(),
            ),
            (
                "general.residency_profile",
                ["economy", "balanced", "ready"][profile.selected() as usize].to_string(),
            ),
            (
                "recognition.server_idle_secs",
                retention.value_as_int().to_string(),
            ),
            (
                "insertion.mode",
                ["automatic", "copy-only", "review"][delivery.selected() as usize].to_string(),
            ),
        ];
        let path = path.clone();
        task(t.clone(), move || {
            settings::update_many(&path, &expected, &updates)?;
            let message = if ipc::request(RequestKind::ConfigReload).is_ok() {
                "Settings saved; model changes apply next session"
            } else {
                "Settings saved; start or restart the daemon to load them"
            };
            Ok(Update::Status(message.into()))
        });
    });
    let unload = button("Unload models", &prefs);
    let sender = tx.clone();
    unload.connect_clicked(move |_| {
        task(sender.clone(), || {
            let response = ipc::request(RequestKind::UnloadModels)?;
            Ok(Update::Status(response.message.unwrap_or_default()))
        })
    });
    add_page(&stack, &prefs, "settings", "Settings");
}
