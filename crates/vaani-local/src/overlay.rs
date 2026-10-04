//! Event-driven layer surface: keyboard focus stays with the dictated editor.
use adw::prelude::*;
use gtk::{glib, glib::translate::ToGlibPtr};
use vaani_core::protocol::RequestKind;

#[link(name = "gtk4-layer-shell")]
extern "C" {
    fn gtk_layer_is_supported() -> i32;
    fn gtk_layer_init_for_window(window: *mut gtk::ffi::GtkWindow);
    fn gtk_layer_set_layer(window: *mut gtk::ffi::GtkWindow, layer: i32);
    fn gtk_layer_set_anchor(window: *mut gtk::ffi::GtkWindow, edge: i32, anchor: i32);
    fn gtk_layer_set_keyboard_mode(window: *mut gtk::ffi::GtkWindow, mode: i32);
}

pub fn run() {
    let app = adw::Application::builder()
        .application_id("org.vaani.Overlay")
        .build();
    app.connect_activate(|app| {
        // A normal toplevel would steal the original editor's focus. Fail closed.
        if unsafe { gtk_layer_is_supported() } == 0 {
            app.quit();
            return;
        }
        let window = gtk::ApplicationWindow::builder()
            .application(app)
            .title("Vaani dictation")
            .decorated(false)
            .default_width(300)
            .build();
        let widget = gtk::Box::new(gtk::Orientation::Vertical, 8);
        widget.set_margin_top(12);
        widget.set_margin_bottom(12);
        widget.set_margin_start(20);
        widget.set_margin_end(20);
        let state = gtk::Label::new(Some("Vaani"));
        widget.append(&state);
        for (title, kind) in [
            ("Finish", RequestKind::Stop),
            ("Cancel", RequestKind::Cancel),
            ("Copy", RequestKind::CopyPending),
        ] {
            let button = gtk::Button::with_label(title);
            widget.append(&button);
            button.connect_clicked(move |_| {
                let kind = kind.clone();
                std::thread::spawn(move || {
                    let _ = crate::ipc::request(kind);
                });
            });
        }
        window.set_child(Some(&widget));
        let ptr = window.upcast_ref::<gtk::Window>().to_glib_none().0;
        // Values are from the stable gtk4-layer-shell C ABI; initialize before mapping.
        unsafe {
            gtk_layer_init_for_window(ptr);
            gtk_layer_set_layer(ptr, 3);
            gtk_layer_set_anchor(ptr, 3, 1);
            gtk_layer_set_keyboard_mode(ptr, 0);
        }
        let (tx, rx) = async_channel::bounded(32);
        std::thread::spawn(move || {
            let _ = crate::ipc::subscribe(|event| tx.send_blocking(event).is_ok());
        });
        let app = app.clone();
        glib::spawn_future_local(async move {
            while let Ok(event) = rx.recv().await {
                if let Some(value) = event.state {
                    state.set_text(&value);
                    if value == "IDLE" {
                        app.quit();
                        break;
                    }
                }
            }
        });
        window.present();
    });
    app.run_with_args::<&str>(&[]);
}
