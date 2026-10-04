# V6 dataset follow-up — 2026-10-04

This note records a source-level follow-up for the next V6 data decision. It
does not authorize downloads, terms acceptance, or treat a dataset's advertised
row/hour count as usable labeled data. Keep all source files and derived audio
outside Git.

## Findings

### Mozilla Common Voice Spontaneous Speech 4.0 — English

The official Mozilla Data Collective catalog lists the English 4.0 release as
CC0-1.0, ASR audio in MP3, approximately 497.82 MB. This is a directly relevant
small source for spontaneous English phenomena (fillers, restarts, repetitions),
but it is not specifically Indian English. It can provide a modest, legally
clear source contribution after the account holder has accepted the applicable
MDC terms and pinned the exact release/datasheet. Do not use the MDC catalog
entry as proof that the local account has accepted terms or acquired the files.

Source: [Mozilla Data Collective spontaneous-speech catalog](https://commonvoice.mozilla.org/fr/datasets).

### NPTEL2020 Indian-English Speech Dataset

AI4Bharat's official repository describes a 2020 crawl of 19,500 NPTEL videos
with manually uploaded subtitles, 6.25 million chunks, and 15,700 reported
hours. The README describes the material as mostly South-Asian-accented English
and technical/general education, which is unusually well matched to Vaani's
Indian-English technical vocabulary. However, it explicitly says the authors
did not manually annotate the corpus and assume NPTEL captions were Google ASR
with some corrections. Its license field says only “Creative Commons,” without
a version or per-video rights evidence. This is therefore a high-value
investigation lead, **not an admitted training source**. Do not fetch its
~100 GB compressed torrent or downloader data until exact license/version,
redistribution/training rights, and source-video permissions are established.
If rights are clarified, start with its small manually annotated “Pure Set” for
evaluation design only, then audit a small training pilot for caption quality
before considering scale. Preserve source/video IDs and exclude duplicate or
overlapping evaluation material.

Source: [AI4Bharat NPTEL2020 repository](https://github.com/AI4Bharat/NPTEL2020-Indian-English-Speech-Dataset).

### IndicVoices

The official AI4Bharat repository currently describes 12,000 hours of natural
read, extempore, and conversational speech across 22 Indian languages and
22,563 speakers, with 3,200 hours transcribed. It is valuable for broader
Indic ASR and future multilingual coverage, but the headline totals are not an
English subset count, and the repository summary does not itself establish the
precise data license/access conditions. For the present Indian-English V6 STT
goal, do not infer English/Hinglish value from multilingual scale. Audit the
English/code-switch rows, transcript status, exact revision, access terms, and
speaker split from the official dataset portal before admission.

Source: [AI4Bharat IndicVoices repository](https://github.com/AI4Bharat/IndicVoices).

### IndicVoices-R

The official repository describes more than 1,700 hours across 22 Indian
languages and 10,000+ speakers, designed as ASR-enhanced TTS data. Its public
README provides download instructions but the checked repository view does
not establish a license grant adequate for Vaani training. It is not an
English-specific ASR source; do not ingest until exact licensing and the
language/label provenance are independently verified.

Source: [AI4Bharat IndicVoices-R repository](https://github.com/AI4Bharat/IndicVoices-R).

## Next actions, in order

1. For near-term spontaneous speech, only acquire the official Common Voice
   Spontaneous English release after MDC account terms are accepted, then
   verify the exact downloaded release manifest and allowed local/off-platform
   processing conditions.
2. Ask the NPTEL dataset maintainers or rights holder to identify the exact
   Creative Commons version and confirm rights for model training, derived
   transcripts, and commercial distribution. Until answered, keep it excluded.
3. Inspect IndicVoices' official English/code-switch configuration and terms
   without downloading; admit only explicitly licensed, transcribed examples
   after source/speaker deduplication and train/dev/test separation.
4. Do not let any of these sources replace the V6 frozen qualification sets.
   Run the same intended Whisper backend on admitted audio, retain source
   reference separately from formatter targets, and report source-wise WER.

No files were downloaded, no terms accepted, and no new examples were added to
the current training run as part of this audit.
