use crate::{add_page, button, column, entry, label, task, Update};
use adw::prelude::*;
use gtk::Orientation;
use vaani_core::protocol::RequestKind;
use vaani_local::ipc;
pub fn build(stack: &gtk::Stack, tx: &async_channel::Sender<Update>) -> gtk::Box {
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
    add_page(&stack, &personal, "personal", "Personalize");
    list
}
