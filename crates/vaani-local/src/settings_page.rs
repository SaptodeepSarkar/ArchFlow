use crate::ui_components::{actions, card};
use crate::{add_page, button, column, entry, label, task, Update};
use adw::prelude::*;
use std::{cell::RefCell, rc::Rc};
use vaani_core::protocol::RequestKind;
use vaani_local::{ipc, settings};
pub fn build(stack: &gtk::Stack, status: &gtk::Label, tx: &async_channel::Sender<Update>) {
    let prefs = column();
    prefs.append(&label("Settings are loaded from your existing file. Saving validates values and preserves comments and unknown fields."));
    let recognition = card(
        "Speech & writing",
        "Choose the model and language you already have installed.",
        "",
    );
    prefs.append(&recognition);
    let selection_row = gtk::Box::new(gtk::Orientation::Horizontal, 16);
    selection_row.set_homogeneous(true);
    recognition.append(&selection_row);
    let language_field = gtk::Box::new(gtk::Orientation::Vertical, 8);
    let model_field = gtk::Box::new(gtk::Orientation::Vertical, 8);
    let language = gtk::DropDown::from_strings(&["English", "Hindi", "Bengali"]);
    let stt_model =
        gtk::DropDown::from_strings(&["tiny", "base", "base.en", "small", "cozy", "v5"]);
    crate::ui_components::field(&model_field, "Installed speech model", &stt_model);
    crate::ui_components::field(&language_field, "Writing language", &language);
    selection_row.append(&model_field);
    selection_row.append(&language_field);
    let delivery = gtk::DropDown::from_strings(&[
        "Type into supported fields",
        "Copy to clipboard",
        "Review first",
    ]);
    crate::ui_components::field(&recognition, "Text delivery", &delivery);
    recognition.append(&label("Optional formatter model"));
    let formatter_path = entry("Path to an installed formatter model", &recognition);
    let residency = card(
        "Model memory",
        "Economy unloads after each use. Choose short retention for quicker repeat sessions.",
        "sky",
    );
    prefs.append(&residency);
    let profile = gtk::DropDown::from_strings(&["economy", "balanced", "ready"]);
    let profiles = gtk::Box::new(gtk::Orientation::Horizontal, 10);
    let mut first = None::<gtk::ToggleButton>;
    for (index, title) in ["Economy", "Balanced", "Ready"].iter().enumerate() {
        let button = gtk::ToggleButton::with_label(title);
        if let Some(group) = &first {
            button.set_group(Some(group));
        } else {
            first = Some(button.clone());
        }
        button.add_css_class("retention-choice");
        let target = profile.clone();
        button.connect_toggled(move |b| {
            if b.is_active() {
                target.set_selected(index as u32);
            }
        });
        let weak = button.downgrade();
        profile.connect_selected_notify(move |p| {
            if let Some(b) = weak.upgrade() {
                b.set_active(p.selected() == index as u32);
            }
        });
        profiles.append(&button);
    }
    first.as_ref().unwrap().set_active(true);
    residency.append(&profiles);
    let retention = gtk::SpinButton::with_range(1.0, 120.0, 1.0);
    retention.set_sensitive(false);
    let idle = retention.clone();
    profile.connect_selected_notify(move |p| idle.set_sensitive(p.selected() != 0));
    crate::ui_components::field(
        &residency,
        "Idle retention seconds (Economy ignores this value)",
        &retention,
    );
    let loaded = Rc::new(RefCell::new(None::<String>));
    let path = vaani_core::config::Config::config_path();
    let controls = actions(&prefs);
    let load = button("Reload settings", &controls);
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
    let save = button("Save settings", &controls);
    save.add_css_class("suggested-action");
    let t = tx.clone();
    let save_status = status.clone();
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
        if let Err(error) = settings::update_many(&path, &expected, &updates) {
            save_status.set_text(&error.to_string());
            return;
        }
        // Refresh the conflict baseline after our own successful save.
        *loaded.borrow_mut() = settings::read(&path).ok().map(|(text, _)| text);
        task(t.clone(), move || {
            let message = if ipc::request(RequestKind::ConfigReload).is_ok() {
                "Settings saved; model changes apply next session"
            } else {
                "Settings saved; start or restart the daemon to load them"
            };
            Ok(Update::Status(message.into()))
        });
    });
    let unload = button("Unload models", &controls);
    let sender = tx.clone();
    unload.connect_clicked(move |_| {
        task(sender.clone(), || {
            let response = ipc::request(RequestKind::UnloadModels)?;
            Ok(Update::Status(response.message.unwrap_or_default()))
        })
    });
    add_page(&stack, &prefs, "settings", "Settings");
}
