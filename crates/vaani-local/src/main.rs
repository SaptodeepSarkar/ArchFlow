mod home_page;
mod models_page;
mod overlay;
mod personalization_page;
mod settings_page;
mod ui_components;
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
use vaani_local::{ipc, pairing, settings};
#[derive(Clone)]
enum Update {
    Status(String),
    Invite(String, String),
    Received(pairing::Bundle),
    ReceiveError(String),
    Personalization(Value),
    Scanned(String),
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
    let b = gtk::Box::new(Orientation::Vertical, 18);
    b.set_margin_top(28);
    b.set_margin_bottom(32);
    b.set_margin_start(32);
    b.set_margin_end(32);
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
    b.set_halign(gtk::Align::Start);
    parent.append(&b);
    b
}
fn add_page(stack: &gtk::Stack, page: &gtk::Box, name: &str, title: &str) {
    let scroll = gtk::ScrolledWindow::new();
    scroll.set_policy(gtk::PolicyType::Never, gtk::PolicyType::Automatic);
    let clamp = adw::Clamp::builder()
        .maximum_size(940)
        .tightening_threshold(720)
        .child(page)
        .build();
    scroll.set_child(Some(&clamp));
    stack.add_titled(&scroll, Some(name), title);
}
fn main() {
    if std::env::args().any(|arg| arg == "--overlay" || arg.starts_with("--overlay-preview=")) {
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
    css.load_from_data(include_str!("native.css"));
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
    header.set_title_widget(Some(&gtk::Label::new(Some("Vaani"))));
    outer.append(&header);
    let content = gtk::Box::new(Orientation::Horizontal, 0);
    let stack = gtk::Stack::new();
    stack.set_hexpand(true);
    stack.set_vexpand(true);
    let sidebar = gtk::Box::new(Orientation::Vertical, 8);
    sidebar.add_css_class("vaani-sidebar");
    sidebar.set_size_request(204, -1);
    let brand = gtk::Box::new(Orientation::Horizontal, 10);
    brand.append(&ui_components::mark(34));
    let name = label("Vaani");
    name.add_css_class("brand-name");
    brand.append(&name);
    sidebar.append(&brand);
    let tagline = label("Your voice. Your words.");
    tagline.add_css_class("muted");
    sidebar.append(&tagline);
    let links = gtk::Box::new(Orientation::Vertical, 8);
    links.set_margin_top(24);
    sidebar.append(&links);
    let pages = [
        (
            "home",
            "Home",
            "go-home-symbolic",
            "Speak freely.",
            "Your voice, without the friction.",
        ),
        (
            "personal",
            "Personalize",
            "edit-find-symbolic",
            "Make Vaani sound like you.",
            "Your spelling. Your phrases. Your everyday shortcuts.",
        ),
        (
            "models",
            "Models",
            "folder-download-symbolic",
            "Make room for your models.",
            "Choose what runs on your device.",
        ),
        (
            "settings",
            "Settings",
            "preferences-system-symbolic",
            "Tune Vaani to your workflow.",
            "A few considered choices. No config editing required.",
        ),
        (
            "devices",
            "Devices",
            "network-workgroup-symbolic",
            "Keep your words close.",
            "Pair nearby devices. Choose what you bring along.",
        ),
    ];
    let page_header = gtk::Box::new(Orientation::Horizontal, 16);
    page_header.add_css_class("page-heading");
    let heading_text = gtk::Box::new(Orientation::Vertical, 5);
    heading_text.set_hexpand(true);
    let page_title = label(pages[0].3);
    page_title.add_css_class("page-title");
    let page_subtitle = label(pages[0].4);
    page_subtitle.add_css_class("muted");
    heading_text.append(&page_title);
    heading_text.append(&page_subtitle);
    page_header.append(&heading_text);
    let local = label("LOCAL FIRST");
    local.add_css_class("local-badge");
    local.set_wrap(false);
    local.set_valign(gtk::Align::Center);
    page_header.append(&local);
    for (id, title, icon, heading, subtitle) in pages {
        let b = gtk::Button::new();
        b.add_css_class("nav-item");
        let row = gtk::Box::new(Orientation::Horizontal, 12);
        row.append(&gtk::Image::from_icon_name(icon));
        row.append(&label(title));
        b.set_child(Some(&row));
        links.append(&b);
        let target = stack.clone();
        b.connect_clicked(move |_| target.set_visible_child_name(id));
        let b = b.clone();
        let title = page_title.clone();
        let sub = page_subtitle.clone();
        stack.connect_visible_child_name_notify(move |stack| {
            if stack.visible_child_name().as_deref() == Some(id) {
                b.add_css_class("selected");
                title.set_text(heading);
                sub.set_text(subtitle);
            } else {
                b.remove_css_class("selected");
            }
        });
    }
    let spacer = gtk::Box::new(Orientation::Vertical, 0);
    spacer.set_vexpand(true);
    sidebar.append(&spacer);
    sidebar.append(&gtk::Separator::new(Orientation::Horizontal));
    let local_caption = label("LOCAL FIRST");
    local_caption.add_css_class("caption");
    sidebar.append(&local_caption);
    let privacy = label("Audio and raw dictation stay on this device.");
    privacy.add_css_class("muted");
    privacy.set_max_width_chars(23);
    sidebar.append(&privacy);
    let main_panel = gtk::Box::new(Orientation::Vertical, 0);
    main_panel.set_hexpand(true);
    main_panel.append(&page_header);
    main_panel.append(&stack);
    let status = label("Open Home to check microphone and models.");
    status.add_css_class("status-bar");
    status.set_max_width_chars(72);
    main_panel.append(&status);
    content.append(&sidebar);
    content.append(&main_panel);
    outer.append(&content);
    window.set_content(Some(&outer));
    let (tx, rx) = async_channel::unbounded::<Update>();
    home_page::build(&stack, &tx);
    settings_page::build(&stack, &status, &tx);
    let list = personalization_page::build(&stack, &tx);
    models_page::build(&stack, &tx);
    let devices = column();
    devices.append(&label("Open both apps on the same reachable local network. Receive displays a two-minute, single-use invitation. Compare the certificate fingerprint before sending. Transfers require approval before merging."));
    let receive_card = ui_components::card("Receive your words", "Show an expiring invitation for the other device to scan. Keep both devices on a reachable local network.", "sky");
    devices.append(&receive_card);
    let host = entry("This device's local IPv4 address", &receive_card);
    let receive = button("Receive / show pairing QR", &receive_card);
    let picture = gtk::Picture::new();
    picture.set_size_request(240, 240);
    picture.set_visible(false);
    receive_card.append(&picture);
    let code = gtk::TextView::new();
    code.set_editable(false);
    code.set_wrap_mode(gtk::WrapMode::Char);
    code.set_visible(false);
    receive_card.append(&code);
    let send_card = ui_components::card(
        "Send to a nearby device",
        "Scan the other device’s invitation, compare fingerprints, then choose what to send.",
        "",
    );
    devices.append(&send_card);
    let invite = entry("Paste the other device's VAANI1 invitation", &send_card);
    let scan = button("Scan pairing QR from image", &send_card);
    let t = tx.clone();
    scan.connect_clicked(move |_| {
        let dialog = gtk::FileChooserNative::new(
            Some("Choose pairing QR image"),
            None::<&gtk::Window>,
            gtk::FileChooserAction::Open,
            Some("Scan"),
            Some("Cancel"),
        );
        let t = t.clone();
        dialog.connect_response(move |dialog, response| {
            if response == gtk::ResponseType::Accept {
                if let Some(path) = dialog.file().and_then(|f| f.path()) {
                    task(t.clone(), move || {
                        anyhow::ensure!(
                            std::fs::metadata(&path)?.len() <= 8 * 1024 * 1024,
                            "QR image exceeds limit"
                        );
                        let mut reader = image::ImageReader::open(path)?.with_guessed_format()?;
                        let mut limits = image::Limits::default();
                        limits.max_image_width = Some(4096);
                        limits.max_image_height = Some(4096);
                        limits.max_alloc = Some(64 * 1024 * 1024);
                        reader.limits(limits);
                        let mut image = rqrr::PreparedImage::prepare(reader.decode()?.to_luma8());
                        for grid in image.detect_grids() {
                            if let Ok((_, text)) = grid.decode() {
                                if pairing::Invitation::parse(&text).is_ok() {
                                    return Ok(Update::Scanned(text));
                                }
                            }
                        }
                        anyhow::bail!("No valid Vaani pairing QR found")
                    });
                }
            }
            dialog.destroy();
        });
        dialog.show();
    });
    let send = button("Send all personalization", &send_card);
    let import_preferences =
        gtk::CheckButton::with_label("Include portable language and retention preferences");
    send_card.append(&import_preferences);
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
    let stop = button("Close receive session", &receive_card);
    let flag = receive_cancel.clone();
    stop.connect_clicked(move |_| {
        flag.store(true, Ordering::Relaxed);
    });
    let flag = receive_cancel.clone();
    stack.connect_visible_child_name_notify(move |stack| {
        if stack.visible_child_name().as_deref() != Some("devices") {
            flag.store(true, Ordering::Relaxed);
        }
    });
    let t = tx.clone();
    let invite_ui = invite.clone();
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
    let approval_card = ui_components::card("You decide what comes in", "Incoming records stay staged until you approve. Existing IDs and deletions are preserved during merge.", "apricot");
    devices.append(&approval_card);
    approval_card.append(&apply_preferences);
    let approve = button("Approve received merge", &approval_card);
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
    add_page(&stack, &devices, "devices", "Devices");
    let t = tx.clone();
    let approve_ui = approve.clone();
    let pending_ui = pending.clone();
    glib::spawn_future_local(async move {
        while let Ok(update) = rx.recv().await {
            match update {
                Update::Status(message) => status.set_text(&message),
                Update::Scanned(text) => {
                    invite_ui.set_text(&text);
                    status.set_text("QR decoded. Compare fingerprints before sending.");
                }
                Update::ReceiveError(message) => {
                    *receive_busy.borrow_mut() = false;
                    status.set_text(&message);
                }
                Update::Invite(text, svg) => {
                    picture.set_visible(true);
                    code.set_visible(true);
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
                                row.add_css_class("personal-row");
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
    stack.set_visible_child_name("home");
    if let Some(page) =
        std::env::args().find_map(|a| a.strip_prefix("--preview-page=").map(str::to_owned))
    {
        stack.set_visible_child_name(&page);
    }
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
