use crate::{
    add_page, button, column, data_dir, entry, task,
    ui_components::{actions, card, field},
    Update,
};
use adw::prelude::*;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use vaani_local::models;

pub fn build(stack: &gtk::Stack, tx: &async_channel::Sender<Update>) {
    let page = column();
    let install_card = card("Choose a model. Make it yours.", "Install a verified speech model or optional formatter. Installing never loads a model into memory.", "sky");
    page.append(&install_card);
    let choices = gtk::DropDown::from_strings(&[
        "Whisper base · Speech",
        "V5 GGUF · Formatter",
        "V6 · Source-grounded formatter",
    ]);
    field(&install_card, "Model to install", &choices);
    let offline = entry(
        "Leave blank to download the verified release",
        &install_card,
    );
    offline.set_tooltip_text(Some(
        "Path to an offline model file. It must match the selected catalog entry’s checksum.",
    ));
    let chooser = button("Choose an offline file…", &install_card);
    let target = offline.clone();
    chooser.connect_clicked(move |_| {
        let dialog = gtk::FileChooserNative::new(
            Some("Choose model file"),
            None::<&gtk::Window>,
            gtk::FileChooserAction::Open,
            Some("Choose"),
            Some("Cancel"),
        );
        let target = target.clone();
        dialog.connect_response(move |d, response| {
            if response == gtk::ResponseType::Accept {
                if let Some(path) = d.file().and_then(|f| f.path()) {
                    target.set_text(&path.to_string_lossy());
                }
            }
            d.destroy();
        });
        dialog.show();
    });
    let advanced = gtk::Expander::new(Some("Custom model catalog"));
    let fields = gtk::Box::new(gtk::Orientation::Vertical, 10);
    let manifest = entry("Local catalog JSON path", &fields);
    let default_catalog = data_dir().join("linux-models.json");
    manifest.set_text(&default_catalog.to_string_lossy());
    let asset_id = entry("Model ID in the catalog", &fields);
    asset_id.set_text("whisper-base-android-starter");
    let selection = asset_id.clone();
    choices.connect_selected_notify(move |choice| {
        selection.set_text(
            [
                "whisper-base-android-starter",
                "vaani-v5-formatter-q8-android",
                "vaani-v6-tagger",
            ][choice.selected() as usize],
        )
    });
    advanced.set_child(Some(&fields));
    install_card.append(&advanced);
    let row = actions(&install_card);
    let install = button("Install verified model", &row);
    install.add_css_class("suggested-action");
    let cancelled = Arc::new(AtomicBool::new(false));
    let busy = Arc::new(AtomicBool::new(false));
    let t = tx.clone();
    let flag = cancelled.clone();
    install.connect_clicked(move |_| {
        if busy.swap(true, Ordering::AcqRel) {
            let _ = t.try_send(Update::Status(
                "A model installation is already running. Cancel it or wait for it to finish."
                    .into(),
            ));
            return;
        }
        let catalog_path = manifest.text().to_string();
        let id = asset_id.text().to_string();
        let file = offline.text().to_string();
        let busy = busy.clone();
        let flag = flag.clone();
        flag.store(false, Ordering::Relaxed);
        let feedback = t.clone();
        let default_catalog = default_catalog.clone();
        task(t.clone(), move || {
            let _lease = InstallLease(busy);
            let catalog = match std::fs::read(&catalog_path) {
                Ok(bytes) => bytes,
                Err(e)
                    if std::path::Path::new(&catalog_path) == default_catalog
                        && e.kind() == std::io::ErrorKind::NotFound =>
                {
                    include_bytes!("../../../models/linux-models.json").to_vec()
                }
                Err(e) => return Err(e.into()),
            };
            let assets: Vec<models::Asset> = serde_json::from_slice(&catalog)?;
            let asset = assets
                .into_iter()
                .find(|asset| asset.id == id)
                .ok_or_else(|| anyhow::anyhow!("Model ID not in catalog"))?;
            let mut last = std::time::Instant::now();
            let progress = move |n| {
                if last.elapsed().as_millis() >= 250 {
                    last = std::time::Instant::now();
                    let _ = feedback.try_send(Update::Status(format!("Downloaded {n} bytes")));
                }
            };
            let path = if file.is_empty() {
                models::download(&asset, &data_dir(), &flag, progress)?
            } else {
                models::install(
                    &asset,
                    std::fs::File::open(file)?,
                    &data_dir(),
                    &flag,
                    progress,
                )?
            };
            Ok(Update::Status(format!(
                "Verified model installed: {}. Select it in Settings.",
                path.display()
            )))
        });
    });
    let cancel = button("Cancel download", &row);
    cancel.connect_clicked(move |_| cancelled.store(true, Ordering::Relaxed));
    page.append(&card("Your existing models stay compatible.", "Verified installs keep the previous model. Vocabulary stays separate. Choose the installed speech model and optional formatter path in Settings.", ""));
    page.append(&card("Memory, on your terms.", "Economy releases models after use. Short retention can make repeat dictations quicker. Choose it in Settings; no model starts loading just because this page is open.", "apricot"));
    add_page(stack, &page, "models", "Models");
}
struct InstallLease(Arc<AtomicBool>);
impl Drop for InstallLease {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}
