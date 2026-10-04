use crate::ui_components::{actions, card};
use crate::{add_page, button, column, entry, label, task, Update};
use adw::prelude::*;
use gtk::Orientation;
use vaani_core::protocol::RequestKind;
use vaani_local::ipc;
pub fn build(stack: &gtk::Stack, tx: &async_channel::Sender<Update>) -> gtk::Box {
    let personal = column();
    personal.append(&label("Vocabulary, snippets, links and replacements are encrypted locally. Links are snippets with a spoken trigger."));
    let editor = card(
        "Your words, recognised properly.",
        "Add a name, a spoken shortcut or a text replacement.",
        "sky",
    );
    personal.append(&editor);
    let kind = gtk::DropDown::from_strings(&["Vocabulary", "Snippet / link", "Replacement"]);
    editor.append(&kind);
    let first = entry("Canonical spelling or spoken trigger", &editor);
    let second = entry(
        "Heard as, snippet value / URL, or replacement text",
        &editor,
    );
    let list = gtk::Box::new(Orientation::Vertical, 6);
    let records = card(
        "Saved words & shortcuts",
        "Refresh to read your encrypted personalization from the service.",
        "",
    );
    personal.append(&records);
    let controls = actions(&editor);
    records.append(&list);
    let t = tx.clone();
    let refresh = button("Refresh personalization", &records);
    refresh.connect_clicked(move |_| {
        task(t.clone(), || {
            Ok(Update::Personalization(
                ipc::request(RequestKind::PersonalizationGet)?
                    .data
                    .unwrap_or_default(),
            ))
        })
    });
    let add = button("Add to my words", &controls);
    add.add_css_class("suggested-action");
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
