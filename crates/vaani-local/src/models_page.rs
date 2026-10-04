use crate::{add_page, button, column, data_dir, entry, label, task, Update};
use adw::prelude::*;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use vaani_local::models;
pub fn build(stack: &gtk::Stack, tx: &async_channel::Sender<Update>) {
    let model_page = column();
    model_page.append(&label("Install a verified model catalog entry. Your existing models remain compatible. Downloads are cached; offline installs verify the same checksums. Installing never loads a model into memory."));
    let manifest = entry(
        "Local catalog JSON path (array of model entries)",
        &model_page,
    );
    manifest.set_text(&data_dir().join("linux-models.json").to_string_lossy());
    let choices = gtk::DropDown::from_strings(&[
        "Whisper base speech",
        "V5 GGUF formatter",
        "V6 source-grounded tagger",
    ]);
    model_page.append(&choices);
    let asset_id = entry("Model ID from catalog", &model_page);
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
    let pack_path = entry(
        "Offline asset file path (leave blank to download)",
        &model_page,
    );
    let cancel = Arc::new(AtomicBool::new(false));
    let install = button("Install verified model", &model_page);
    let t = tx.clone();
    let flag = cancel.clone();
    install.connect_clicked(move |_|{let manifest=manifest.text().to_string();let id=asset_id.text().to_string();let local=pack_path.text().to_string();let flag=flag.clone();flag.store(false,Ordering::Relaxed);let feedback=t.clone();task(t.clone(),move||{let catalog=std::fs::read(manifest).unwrap_or_else(|_|include_bytes!("../../../models/linux-models.json").to_vec());let assets:Vec<models::Asset>=serde_json::from_slice(&catalog)?;let asset=assets.into_iter().find(|a|a.id==id).ok_or_else(||anyhow::anyhow!("Model ID not in catalog"))?;let root=data_dir();let mut last=std::time::Instant::now();let progress=move|n|{if last.elapsed().as_millis()>=250 {last=std::time::Instant::now();let _=feedback.try_send(Update::Status(format!("Downloaded {n} bytes")));}};let path=if local.is_empty(){models::download(&asset,&root,&flag,progress)?}else{models::install(&asset,std::fs::File::open(local)?,&root,&flag,progress)?};Ok(Update::Status(format!("Verified model installed: {}. Select its model name in settings or use the documented backend configuration.",path.display())))});});
    let cancel_button = button("Cancel download", &model_page);
    cancel_button.connect_clicked(move |_| cancel.store(true, Ordering::Relaxed));
    add_page(&stack, &model_page, "models", "Models");
}
