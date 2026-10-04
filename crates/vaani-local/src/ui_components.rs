//! Shared native components matching the spacing and hierarchy of SettingsView.qml.
use adw::prelude::*;
use gtk::{glib, Orientation};

pub fn card(title: &str, description: &str, tone: &str) -> gtk::Box {
    let card = gtk::Box::new(Orientation::Vertical, 12);
    card.add_css_class("vaani-card");
    if !tone.is_empty() {
        card.add_css_class(tone);
    }
    let heading = crate::label(title);
    heading.add_css_class("section-title");
    card.append(&heading);
    if !description.is_empty() {
        let description = crate::label(description);
        description.add_css_class("muted");
        card.append(&description);
    }
    card
}

pub fn field(parent: &gtk::Box, title: &str, widget: &impl IsA<gtk::Widget>) {
    let title = crate::label(title);
    title.add_css_class("field-label");
    parent.append(&title);
    widget.set_hexpand(true);
    parent.append(widget);
}

pub fn actions(parent: &gtk::Box) -> gtk::Box {
    let row = gtk::Box::new(Orientation::Horizontal, 10);
    row.set_margin_top(8);
    parent.append(&row);
    row
}

pub fn mark(size: i32) -> gtk::Picture {
    let stream = gtk::gio::MemoryInputStream::from_bytes(&glib::Bytes::from_static(
        include_bytes!("../../../brand/vaani-mark.svg"),
    ));
    let image = gtk::Picture::new();
    if let Ok(pixbuf) = gtk::gdk_pixbuf::Pixbuf::from_stream_at_scale(
        &stream,
        size,
        size,
        true,
        None::<&gtk::gio::Cancellable>,
    ) {
        image.set_pixbuf(Some(&pixbuf));
    }
    image.set_size_request(size, size);
    image.set_halign(gtk::Align::Start);
    image
}
