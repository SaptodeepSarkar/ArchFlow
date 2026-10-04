mod overlay;
use adw::prelude::*;
use gtk::{glib, Orientation};
use serde_json::Value;
use std::{
    cell::RefCell,
    rc::Rc,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};
use vaani_core::protocol::{PersonalizationEntity, RequestKind};
use vaani_local::{ipc, models, pairing, settings};
#[derive(Clone)]
enum Update {
    Status(String),
    Invite(String, String),
    Received(pairing::Bundle),
    ReceiveError(String),
    Personalization(Value),
}
fn data_dir() -> std::path::PathBuf {
    std::env::var_os("XDG_DATA_HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| {
            std::path::PathBuf::from(std::env::var("HOME").unwrap_or_default()).join(".local/share")
        })
        .join("vaani")
}
fn task(
    tx: async_channel::Sender<Update>,
    work: impl FnOnce() -> anyhow::Result<Update> + Send + 'static,
) {
    std::thread::spawn(move || {
        let result = work().unwrap_or_else(|e| Update::Status(e.to_string()));
        let _ = tx.send_blocking(result);
    });
}
fn column() -> gtk::Box {
    let b = gtk::Box::new(Orientation::Vertical, 12);
    b.set_margin_top(20);
    b.set_margin_bottom(20);
    b.set_margin_start(24);
    b.set_margin_end(24);
    b
}
fn label(text: &str) -> gtk::Label {
    let l = gtk::Label::new(Some(text));
    l.set_wrap(true);
    l.set_xalign(0.0);
    l
}
fn entry(placeholder: &str, parent: &gtk::Box) -> gtk::Entry {
    let e = gtk::Entry::new();
    e.set_placeholder_text(Some(placeholder));
    parent.append(&e);
    e
}
fn button(text: &str, parent: &gtk::Box) -> gtk::Button {
    let b = gtk::Button::with_label(text);
    parent.append(&b);
    b
}
fn main() {
    if std::env::args().any(|arg| arg == "--overlay") {
        overlay::run();
        return;
    }
    let app = adw::Application::builder()
        .application_id("org.vaani.Desktop")
        .build();
    app.connect_activate(build);
    app.run_with_args::<&str>(&[]);
}
fn build(app: &adw::Application) {
    let smoke = std::env::args().any(|a| a == "--smoke-test");
    let css = gtk::CssProvider::new();
    css.load_from_data("window {background:#fafaf7;color:#202b36;} .suggested-action {background:#226ea8;color:white;} .sidebar {background:#e4f2ff;} entry {border-radius:8px;} .title-1 {color:#226ea8;}");
    gtk::style_context_add_provider_for_display(
        &gtk::gdk::Display::default().expect("display"),
        &css,
        gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
    );
    adw::StyleManager::default().set_color_scheme(adw::ColorScheme::ForceLight);
    let window = adw::ApplicationWindow::builder()
        .application(app)
        .title("Vaani — Your voice, your device")
        .default_width(920)
        .default_height(680)
        .build();
    let outer = gtk::Box::new(Orientation::Vertical, 0);
    let header = adw::HeaderBar::new();
    header.set_title_widget(Some(&label("Vaani")));
    outer.append(&header);
    let content = gtk::Box::new(Orientation::Horizontal, 0);
    let stack = gtk::Stack::new();
    stack.set_hexpand(true);
    stack.set_vexpand(true);
    let sidebar = gtk::StackSidebar::new();
    sidebar.set_stack(&stack);
    sidebar.add_css_class("sidebar");
    content.append(&sidebar);
    content.append(&stack);
    outer.append(&content);
    let status = label("Ready. Open Home to check microphone and models.");
    status.set_margin_start(24);
    status.set_margin_end(24);
    status.set_margin_bottom(12);
    outer.append(&status);
    window.set_content(Some(&outer));
    let (tx, rx) = async_channel::unbounded::<Update>();
    let home = column();
    let title = label("Speak naturally. Vaani writes.");
    title.add_css_class("title-1");
    home.append(&title);
    home.append(&label(
        "Local dictation. Models load only when needed. Economy unloads after use.",
    ));
    let dictate = button("Start / finish dictation", &home);
    dictate.add_css_class("suggested-action");
    let t = tx.clone();
    dictate.connect_clicked(move |_| {
        task(t.clone(), || {
            ipc::request(RequestKind::Toggle)?;
            Ok(Update::Status("Dictation request sent".into()))
        })
    });
    for (text, kind) in [
        ("Cancel", RequestKind::Cancel),
        ("Copy pending text", RequestKind::CopyPending),
        ("Check capabilities", RequestKind::Doctor),
    ] {
        let b = button(text, &home);
        let t = tx.clone();
        b.connect_clicked(move |_| {
            let kind = kind.clone();
            task(t.clone(), move || {
                let response = ipc::request(kind)?;
                Ok(Update::Status(
                    response
                        .data
                        .map(|d| d.to_string())
                        .unwrap_or_else(|| "Done".into()),
                ))
            })
        });
    }
    for (text, command) in [
        ("Start background service", "start"),
        ("Stop background service", "stop"),
    ] {
        let b = button(text, &home);
        let t = tx.clone();
        b.connect_clicked(move |_| {
            task(t.clone(), move || {
                anyhow::ensure!(
                    std::process::Command::new("systemctl")
                        .args(["--user", command, "vaanid.service"])
                        .status()?
                        .success(),
                    "Service action failed. Check installation and your user session."
                );
                Ok(Update::Status(format!("Service {command} requested")))
            })
        });
    }
    stack.add_titled(&home, Some("home"), "Home");
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
    stack.add_titled(&prefs, Some("settings"), "Settings");
    let personal = column();
    personal.append(&label("Vocabulary, snippets, links and replacements are encrypted locally. Links are snippets with a spoken trigger."));
    let kind = gtk::DropDown::from_strings(&["Vocabulary", "Snippet / link", "Replacement"]);
    personal.append(&kind);
    let first = entry("Canonical spelling or spoken trigger", &personal);
    let second = entry(
        "Heard as, snippet value / URL, or replacement text",
        &personal,
    );
    let list = gtk::Box::new(Orientation::Vertical, 6);
    let scroll = gtk::ScrolledWindow::builder()
        .child(&list)
        .vexpand(true)
        .build();
    personal.append(&scroll);
    let t = tx.clone();
    let refresh = button("Refresh personalization", &personal);
    refresh.connect_clicked(move |_| {
        task(t.clone(), || {
            Ok(Update::Personalization(
                ipc::request(RequestKind::PersonalizationGet)?
                    .data
                    .unwrap_or_default(),
            ))
        })
    });
    let add = button("Add", &personal);
    let t = tx.clone();
    add.connect_clicked(move |_| {
        let first = first.text().to_string();
        let second = second.text().to_string();
        let index = kind.selected();
        task(t.clone(), move || {
            let request = match index {
                0 => RequestKind::PersonalizationAddVocabulary {
                    canonical: first,
                    spoken_alias: Some(second),
                    category: Some("personal".into()),
                },
                1 => RequestKind::PersonalizationAddSnippet {
                    trigger: first,
                    value: second,
                },
                _ => RequestKind::PersonalizationAddReplacement {
                    source: first,
                    target: second,
                },
            };
            ipc::request(request)?;
            Ok(Update::Personalization(
                ipc::request(RequestKind::PersonalizationGet)?
                    .data
                    .unwrap_or_default(),
            ))
        });
    });
    stack.add_titled(&personal, Some("personal"), "Personalize");
    let model_page = column();
    model_page.append(&label("Install a verified model catalog entry. Your existing models remain compatible. Downloads are cached; offline installs verify the same checksums. Installing never loads a model into memory."));
    let manifest = entry(
        "Local catalog JSON path (array of model entries)",
        &model_page,
    );
    let asset_id = entry("Model ID from catalog", &model_page);
    let pack_path = entry(
        "Offline asset file path (leave blank to download)",
        &model_page,
    );
    let cancel = Arc::new(AtomicBool::new(false));
    let install = button("Install verified model", &model_page);
    let t = tx.clone();
    let flag = cancel.clone();
    install.connect_clicked(move |_|{let manifest=manifest.text().to_string();let id=asset_id.text().to_string();let local=pack_path.text().to_string();let flag=flag.clone();flag.store(false,Ordering::Relaxed);let feedback=t.clone();task(t.clone(),move||{let assets:Vec<models::Asset>=serde_json::from_slice(&std::fs::read(manifest)?)?;let asset=assets.into_iter().find(|a|a.id==id).ok_or_else(||anyhow::anyhow!("Model ID not in catalog"))?;let root=data_dir();let progress=move|n|{let _=feedback.try_send(Update::Status(format!("Downloaded {n} bytes")));};let path=if local.is_empty(){models::download(&asset,&root,&flag,progress)?}else{models::install(&asset,std::fs::File::open(local)?,&root,&flag,progress)?};Ok(Update::Status(format!("Verified model installed: {}. Select its model name in settings or use the documented backend configuration.",path.display())))});});
    let cancel_button = button("Cancel download", &model_page);
    cancel_button.connect_clicked(move |_| cancel.store(true, Ordering::Relaxed));
    stack.add_titled(&model_page, Some("models"), "Models");
    let devices = column();
    devices.append(&label("Open both apps on the same reachable local network. Receive displays a two-minute, single-use invitation. Compare the certificate fingerprint before sending. Transfers require approval before merging."));
    let host = entry("This device's local IPv4 address", &devices);
    let receive = button("Receive / show pairing QR", &devices);
    let picture = gtk::Picture::new();
    picture.set_size_request(240, 240);
    devices.append(&picture);
    let code = gtk::TextView::new();
    code.set_editable(false);
    code.set_wrap_mode(gtk::WrapMode::Char);
    devices.append(&code);
    let invite = entry("Paste the other device's VAANI1 invitation", &devices);
    let send = button("Send all personalization", &devices);
    let import_preferences =
        gtk::CheckButton::with_label("Include portable language and retention preferences");
    devices.append(&import_preferences);
    let pending = Rc::new(RefCell::new(None::<pairing::Bundle>));
    let receive_cancel = Arc::new(AtomicBool::new(false));
    let t = tx.clone();
    let flag = receive_cancel.clone();
    let receive_busy = Rc::new(RefCell::new(false));
    let busy = receive_busy.clone();
    receive.connect_clicked(move |_| {
        if *busy.borrow() {
            return;
        }
        *busy.borrow_mut() = true;
        let address = host.text().to_string();
        let flag = flag.clone();
        flag.store(false, Ordering::Relaxed);
        let t = t.clone();
        std::thread::spawn(move || {
            let result = (|| {
                let receiver = pairing::Receiver::new(&address)?;
                t.send_blocking(Update::Invite(
                    receiver.invitation.encode()?,
                    receiver.invitation.qr_svg()?,
                ))?;
                receiver.receive(&flag)
            })();
            let update = match result {
                Ok(bundle) => Update::Received(bundle),
                Err(e) => Update::ReceiveError(e.to_string()),
            };
            let _ = t.send_blocking(update);
        });
    });
    let stop = button("Close receive session", &devices);
    let flag = receive_cancel.clone();
    let busy = receive_busy.clone();
    stop.connect_clicked(move |_| {
        flag.store(true, Ordering::Relaxed);
        *busy.borrow_mut() = false;
    });
    let t = tx.clone();
    send.connect_clicked(move |_| {
        let text = invite.text().to_string();
        let include = import_preferences.is_active();
        task(t.clone(), move || {
            let invitation = pairing::Invitation::parse(&text)?;
            let mut bundle: pairing::Bundle = serde_json::from_value(
                ipc::request(RequestKind::PersonalizationExport)?
                    .data
                    .unwrap_or_default(),
            )?;
            if !include {
                bundle.preferences.clear();
            }
            pairing::send(&invitation, &bundle)?;
            Ok(Update::Status(
                "Transfer delivered; waiting for the receiver to approve the merge".into(),
            ))
        });
    });
    let apply_preferences =
        gtk::CheckButton::with_label("Apply received portable preferences when approving");
    devices.append(&apply_preferences);
    let approve = button("Approve received merge", &devices);
    approve.set_sensitive(false);
    let t = tx.clone();
    let staged = pending.clone();
    approve.connect_clicked(move |_| {
        let Some(bundle) = staged.borrow_mut().take() else { return; };
        let apply = apply_preferences.is_active();
        task(t.clone(), move || {
            if apply && !bundle.preferences.is_empty() {
                let path = vaani_core::config::Config::config_path();
                let (text, _) = settings::read(&path)?;
                let updates: Vec<(&str, String)> = bundle.preferences.iter().map(|(k,v)|(k.as_str(),v.clone())).collect();
                settings::update_many(&path, &text, &updates)?;
                ipc::request(RequestKind::ConfigReload)?;
            }
            ipc::request(RequestKind::PersonalizationImport { records: bundle.records })?;
            Ok(Update::Status("Received personalization merged. Reload Settings to view any approved preference changes.".into()))
        });
    });
    stack.add_titled(&devices, Some("devices"), "Devices");
    let t = tx.clone();
    let approve_ui = approve.clone();
    let pending_ui = pending.clone();
    glib::spawn_future_local(async move {
        while let Ok(update) = rx.recv().await {
            match update {
                Update::Status(message) => status.set_text(&message),
                Update::ReceiveError(message) => {
                    *receive_busy.borrow_mut() = false;
                    status.set_text(&message);
                }
                Update::Invite(text, svg) => {
                    code.buffer().set_text(&text);
                    let bytes = glib::Bytes::from_owned(svg.into_bytes());
                    let stream = gtk::gio::MemoryInputStream::from_bytes(&bytes);
                    if let Ok(pixbuf) = gtk::gdk_pixbuf::Pixbuf::from_stream(
                        &stream,
                        None::<&gtk::gio::Cancellable>,
                    ) {
                        picture.set_pixbuf(Some(&pixbuf));
                    }
                    status.set_text("Invitation ready; expires in two minutes.");
                }
                Update::Received(bundle) => {
                    *receive_busy.borrow_mut() = false;
                    status.set_text(&format!("Received {} records. Portable preferences: {:?}. Approve to merge; existing IDs and deletions are preserved.",bundle.records.len(),bundle.preferences));
                    *pending_ui.borrow_mut() = Some(bundle);
                    approve_ui.set_sensitive(true);
                }
                Update::Personalization(value) => {
                    while let Some(child) = list.first_child() {
                        list.remove(&child);
                    }
                    for (name, entity, field) in [
                        ("vocabulary", PersonalizationEntity::Vocabulary, "canonical"),
                        ("snippets", PersonalizationEntity::Snippet, "trigger"),
                        ("replacements", PersonalizationEntity::Replacement, "source"),
                    ] {
                        if let Some(items) = value["personalization"][name].as_array() {
                            for item in items {
                                let row = gtk::Box::new(Orientation::Horizontal, 8);
                                let l = label(item[field].as_str().unwrap_or("Entry"));
                                l.set_hexpand(true);
                                row.append(&l);
                                let remove = gtk::Button::with_label("Remove");
                                row.append(&remove);
                                let id = item["id"].as_str().unwrap_or_default().to_string();
                                let t = t.clone();
                                remove.connect_clicked(move |_| {
                                    let id = id.clone();
                                    task(t.clone(), move || {
                                        ipc::request(RequestKind::PersonalizationRemove {
                                            entity,
                                            id,
                                        })?;
                                        Ok(Update::Personalization(
                                            ipc::request(RequestKind::PersonalizationGet)?
                                                .data
                                                .unwrap_or_default(),
                                        ))
                                    });
                                });
                                list.append(&row);
                            }
                        }
                    }
                    status.set_text("Personalization loaded");
                }
            }
        }
    });
    let flag = receive_cancel;
    window.connect_close_request(move |_| {
        flag.store(true, Ordering::Relaxed);
        glib::Propagation::Proceed
    });
    window.present();
    if smoke {
        let app = app.clone();
        glib::idle_add_local_once(move || {
            assert_eq!(stack.pages().n_items(), 5);
            stack.set_visible_child_name("settings");
            assert_eq!(stack.visible_child_name().as_deref(), Some("settings"));
            println!(
                "Native GTK application constructed five feature pages and switched to Settings"
            );
            app.quit();
        });
    }
}
