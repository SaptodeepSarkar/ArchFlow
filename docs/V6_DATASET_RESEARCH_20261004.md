# V6 dataset follow-up — 2026-10-04

This note records a source-level follow-up for the next V6 data decision. It
does not authorize downloads, terms acceptance, or treat a dataset's advertised
row/hour count as usable labeled data. Keep all source files and derived audio
outside Git.

## Findings

### Mozilla Common Voice Spontaneous Speech 5.0 — English

The official Mozilla Data Collective datasheet lists the English 5.0 release
as CC0-1.0, ASR audio in MP3, 519.05 MB. The datasheet reports 5,898 clips
(18.6 hours total; 8.39 hours validated), but only 1,569 validated clips are in
the train split; the 548 dev and 357 test clips must remain out of training.
Examples include fillers, restarts, repetitions, and hesitation. This is a
directly relevant source for spontaneous English, but it is not specifically
Indian English. The release disallows speaker identification and re-hosting.
Acquire only after the account holder has accepted applicable MDC terms and
checked permitted local/off-platform processing; pin the exact release and
manifest. The datasheet is not proof that the local account accepted terms or
acquired the files.

Source: [Mozilla Data Collective Spontaneous Speech 5.0 English datasheet](https://mozilladatacollective.com/datasets/cmu5nqn1h00vwmi07b4dbk085).

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

Additional license check: NPTEL's current official homepage describes its
materials as Creative Commons Attribution-ShareAlike and also displays “CC BY -
NC - SA”; the dataset README does not identify a version or resolve this
noncommercial restriction. YouTube's own help distinguishes its standard
license from CC BY and says YouTube cannot grant rights to a creator's video.
This reinforces **do not admit** the NPTEL crawl or derivatives to Vaani's
intended model release unless NPTEL/each rights holder provides an applicable
commercial-training and redistribution grant.

Sources: [AI4Bharat NPTEL2020 repository](https://github.com/AI4Bharat/NPTEL2020-Indian-English-Speech-Dataset), [NPTEL official site](https://www.nptel.org.in/), [YouTube license guidance](https://support.google.com/youtube/answer/2797468).

### SPIRE-SIES — spontaneous Indian English

The IISc SPIRE portal describes SPIRE-SIES as 170+ hours / 1,607 speakers of
spontaneous Indian English and requires a three-step access form. Its paper
reports 170.83 hours collected but only about 23 hours of generated-and-
validated transcripts, so supervised ASR scale is much smaller than the audio
headline. The portal's general terms do not grant a dataset license: they say
use of site materials is not allowed except as specifically authorized. No
dataset-specific license, model-training grant, commercial-use permission, or
redistribution right was visible during this audit. Mark it **deferred** until
SPIRE Lab supplies written terms and authorized access; do not submit a form or
download data on the user's behalf because the form requests personal/contact
information and a purpose statement.

Sources: [SPIRE-SIES access page](https://spiredatasets.ee.iisc.ac.in/spiresiescorpus), [SPIRE-SIES paper](https://arxiv.org/abs/2312.00698), [SPIRE portal terms](https://spiredatasets.ee.iisc.ac.in/termsandconditions).

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
3. Request SPIRE-SIES dataset-specific license, commercial-training,
   redistribution, transcript-split, and speaker-ID terms from SPIRE Lab before
   access; keep it deferred until then.
4. Inspect IndicVoices' official English/code-switch configuration and terms
   without downloading; admit only explicitly licensed, transcribed examples
   after source/speaker deduplication and train/dev/test separation.
5. Do not let any of these sources replace the V6 frozen qualification sets.
   Run the same intended Whisper backend on admitted audio, retain source
   reference separately from formatter targets, and report source-wise WER.

No files were downloaded, no terms accepted, and no new examples were added to
the current training run as part of this audit.
