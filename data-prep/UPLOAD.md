# Upload the data bundle to Colab

The bundle is `.data/v8/bundles/vaani-v8-data.tar.zst` (about 5–6 GB) plus
`.sha256`. It contains `stt/`, `formatter/`, `manifest.json`, `SHA256SUMS`.

1. Upload the `.tar.zst` to Google Drive (any folder).
2. Right-click → Share → **Anyone with the link** (or keep it private and use
   the Drive mount; `gdown` needs a link-accessible file).
3. Copy the file id from the link: `https://drive.google.com/file/d/<ID>/view`.
4. On Colab:

```bash
export VAANI_DATA_URL='<ID>'
export VAANI_DATA_SHA256='<first field of vaani-v8-data.tar.zst.sha256>'
bash training/bootstrap_colab.sh
```

`bootstrap_colab.sh` also accepts a direct `https://` URL. It downloads to
`/content/vaani-v8-data.tar.zst`, verifies the sha256, and extracts to
`/content/vaani-data`. Expected layout after extraction:

```
/content/vaani-data/stt/train.jsonl
/content/vaani-data/stt/audio/train/*.wav
/content/vaani-data/formatter/train.jsonl
```

If `VAANI_DATA_URL` is unset, the script expects `VAANI_DATA_DIR` to already
contain that layout (e.g. a mounted Drive folder) and only checks row counts.
