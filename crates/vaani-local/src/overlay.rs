//! On-demand, event-driven layer surface. The daemon owns capture and delivery.
use adw::prelude::*;
use gtk::{glib, glib::translate::ToGlibPtr};
use std::{cell::RefCell, rc::Rc, time::Duration};
use vaani_core::protocol::{Event, RequestKind};
use vaani_local::hud_state::HudState;

#[link(name = "gtk4-layer-shell")]
extern "C" {
    fn gtk_layer_is_supported() -> i32;
    fn gtk_layer_init_for_window(window: *mut gtk::ffi::GtkWindow);
    fn gtk_layer_set_layer(window: *mut gtk::ffi::GtkWindow, layer: i32);
    fn gtk_layer_set_anchor(window: *mut gtk::ffi::GtkWindow, edge: i32, anchor: i32);
    fn gtk_layer_set_keyboard_mode(window: *mut gtk::ffi::GtkWindow, mode: i32);
    fn gtk_layer_set_margin(window: *mut gtk::ffi::GtkWindow, edge: i32, margin: i32);
    fn gtk_layer_set_exclusive_zone(window: *mut gtk::ffi::GtkWindow, zone: i32);
}
enum Update {
    Event(Event),
    Disconnected,
}

pub fn run() {
    // Explicit visual-review mode has no daemon connection and disabled controls.
    let preview =
        std::env::args().find_map(|a| a.strip_prefix("--overlay-preview=").map(str::to_owned));
    let app = adw::Application::builder()
        .application_id("org.vaani.Overlay")
        .flags(gtk::gio::ApplicationFlags::NON_UNIQUE)
        .build();
    app.connect_activate(move |app| {
        // Never substitute a focus-stealing normal window in production.
        if preview.is_none() && unsafe { gtk_layer_is_supported() } == 0 {
            app.quit();
            return;
        }
        let css = gtk::CssProvider::new();
        css.load_from_data(include_str!("overlay.css"));
        gtk::style_context_add_provider_for_display(
            &gtk::gdk::Display::default().expect("display"),
            &css,
            gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
        );
        let window = gtk::ApplicationWindow::builder()
            .application(app)
            .title("Vaani dictation")
            .decorated(false)
            .default_width(440)
            .resizable(false)
            .build();
        window.add_css_class("vaani-hud");
        let frame = gtk::Box::new(gtk::Orientation::Vertical, 0);
        frame.set_margin_top(4);
        frame.set_margin_bottom(4);
        frame.set_margin_start(4);
        frame.set_margin_end(4);
        let card = gtk::Box::new(gtk::Orientation::Horizontal, 13);
        card.add_css_class("hud-card");
        frame.append(&card);
        let model = Rc::new(RefCell::new(HudState::default()));
        let wave = gtk::DrawingArea::new();
        wave.set_content_width(44);
        wave.set_content_height(44);
        wave.add_css_class("hud-wave");
        let state = model.clone();
        wave.set_draw_func(move |_, cr, width, height| {
            cr.set_source_rgb(0.157, 0.427, 0.624);
            for (i, level) in state.borrow().levels.iter().enumerate() {
                let h = 4.0 + 24.0 * (*level as f64 * 6.0).min(1.0).powf(0.6);
                let x = width as f64 / 2.0 + (i as f64 - 2.0) * 5.0;
                cr.set_line_width(3.0);
                cr.set_line_cap(gtk::cairo::LineCap::Round);
                cr.move_to(x, (height as f64 - h) / 2.0);
                cr.line_to(x, (height as f64 + h) / 2.0);
                let _ = cr.stroke();
            }
        });
        card.append(&wave);
        let text = gtk::Box::new(gtk::Orientation::Vertical, 4);
        text.set_hexpand(true);
        text.set_valign(gtk::Align::Center);
        let caption = gtk::Label::new(Some("CONNECTING"));
        caption.add_css_class("hud-caption");
        caption.set_xalign(0.0);
        let line = gtk::Label::new(Some("Connecting to Vaani…"));
        line.add_css_class("hud-line");
        line.set_xalign(0.0);
        line.set_ellipsize(gtk::pango::EllipsizeMode::End);
        line.set_max_width_chars(32);
        text.append(&caption);
        text.append(&line);
        card.append(&text);
        let finish = action(
            "media-playback-stop-symbolic",
            "Finish dictation",
            RequestKind::Stop,
            &card,
            &model,
            preview.is_some(),
        );
        let copy = action(
            "edit-copy-symbolic",
            "Copy pending text",
            RequestKind::CopyPending,
            &card,
            &model,
            preview.is_some(),
        );
        copy.set_visible(false);
        let cancel = action(
            "window-close-symbolic",
            "Cancel dictation",
            RequestKind::Cancel,
            &card,
            &model,
            preview.is_some(),
        );
        cancel.add_css_class("cancel");
        window.set_child(Some(&frame));
        if preview.is_none() {
            let ptr = window.upcast_ref::<gtk::Window>().to_glib_none().0;
            // Stable C ABI: overlay=3, bottom=3, keyboard mode=None=0.
            unsafe {
                gtk_layer_init_for_window(ptr);
                gtk_layer_set_layer(ptr, 3);
                gtk_layer_set_anchor(ptr, 3, 1);
                gtk_layer_set_keyboard_mode(ptr, 0);
                gtk_layer_set_margin(ptr, 3, 24);
                gtk_layer_set_exclusive_zone(ptr, 0);
            }
        }
        let (tx, rx) = async_channel::bounded(32);
        if let Some(state) = &preview {
            let _ = tx.try_send(Update::Event(Event {
                protocol_version: 1,
                event: "state".into(),
                session_id: Some("visual-review".into()),
                state: Some(state.to_uppercase()),
                amplitude: None,
                message: None,
                data: None,
            }));
        } else {
            std::thread::spawn(move || {
                let _ =
                    crate::ipc::subscribe(|event| tx.send_blocking(Update::Event(event)).is_ok());
                let _ = tx.send_blocking(Update::Disconnected);
            });
        }
        let app = app.clone();
        let visual_review = preview.is_some();
        let timer = Rc::new(RefCell::new(None::<glib::SourceId>));
        glib::spawn_future_local(async move {
            while let Ok(update) = rx.recv().await {
                let event = match update {
                    Update::Event(e) => e,
                    Update::Disconnected => {
                        app.quit();
                        break;
                    }
                };
                if event.state.as_deref() == Some("STARTING")
                    && model
                        .borrow()
                        .session
                        .as_ref()
                        .zip(event.session_id.as_ref())
                        .is_some_and(|(a, b)| a != b)
                {
                    app.quit();
                    break;
                }
                if !model.borrow_mut().apply(&event) {
                    continue;
                }
                let current = model.borrow();
                let (title, detail) = current.caption();
                caption.set_text(title);
                line.set_text(detail);
                wave.queue_draw();
                finish.set_visible(matches!(current.state.as_str(), "STARTING" | "RECORDING"));
                finish.set_sensitive(!visual_review && current.state == "RECORDING");
                copy.set_visible(current.state == "READY");
                copy.set_sensitive(!visual_review);
                cancel.set_visible(matches!(
                    current.state.as_str(),
                    "STARTING" | "RECORDING" | "TRANSCRIBING" | "CLEANING" | "READY"
                ));
                cancel.set_sensitive(!visual_review);
                if let Some(old) = timer.borrow_mut().take() {
                    old.remove();
                }
                if !visual_review {
                    if let Some(ms) = current.dismissal_ms() {
                        let app = app.clone();
                        let handle = timer.clone();
                        *timer.borrow_mut() = Some(glib::timeout_add_local_once(
                            Duration::from_millis(ms),
                            move || {
                                handle.borrow_mut().take();
                                app.quit();
                            },
                        ));
                    }
                }
            }
        });
        window.present();
    });
    app.run_with_args::<&str>(&[]);
}
fn action(
    icon: &str,
    title: &str,
    kind: RequestKind,
    parent: &gtk::Box,
    model: &Rc<RefCell<HudState>>,
    preview: bool,
) -> gtk::Button {
    let button = gtk::Button::from_icon_name(icon);
    button.add_css_class("hud-action");
    button.set_tooltip_text(Some(title));
    button.set_focusable(false);
    button.set_sensitive(!preview);
    button.update_property(&[gtk::accessible::Property::Label(title)]);
    parent.append(&button);
    let model = model.clone();
    button.connect_clicked(move |_| {
        let session = model.borrow().session.clone();
        let kind = kind.clone();
        // Never dispatch before the initial session snapshot has arrived.
        if session.is_none() {
            return;
        }
        std::thread::spawn(move || {
            let _ = crate::ipc::request_for_session(kind, session);
        });
    });
    button
}
