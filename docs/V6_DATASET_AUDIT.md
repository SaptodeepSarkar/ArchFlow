# V6 Dataset Audit

Audit date: 2026-09-23. This is a licensing and suitability audit, not a
download log. “Accepted” means suitable for controlled future ingestion after
the stated release is fetched and rechecked; it does not mean records have
been downloaded or processed. Unclear, restricted, or incompatible terms are
rejected pending a new audit.

| Candidate | Authoritative source / version | License, training, redistribution | Media and annotations | V6 contribution / limitation | Decision |
| --- | --- | --- | --- | --- | --- |
| Mozilla Common Voice Spontaneous Speech English | [Mozilla Data Collective dataset](https://mozilladatacollective.com/datasets/cmn1pv5hi00uto1072y1074y7), Spontaneous Speech 3.0 | CC0-1.0; training/commercial use allowed. Mozilla asks consumers not to mirror the package outside MDC. Download requires an MDC API credential and explicit acceptance of dataset terms. | Catalog lists English MP3 ASR data (459.05 MB); spontaneous responses, transcript metadata; no repair labels or guaranteed word timings. | Open natural short speech for actual-STT hypotheses and manual review; group by contributor where available. | ACCEPTED for controlled ingestion; acquisition blocked pending authorized MDC access. |
| Mozilla Common Voice scripted English / Indian accent | [Common Voice terms](https://commonvoice.mozilla.org/terms); pin exact release before acquisition | CC0 unless otherwise specified; commercial use allowed; no third-party mirror. | Audio/text and contributor metadata where released; scripted, no repair labels. | Indian-English STT corruption, capitalization, and technical text after reviewed target creation; not formatter ground truth by itself. | ACCEPTED. |
| AMI Meeting Corpus | [AMI corpus](https://groups.inf.ed.ac.uk/ami/corpus/), 100 hours; [download](https://groups.inf.ed.ac.uk/ami/download/) manual annotation v1.6.2 (2017-04-10) | Official page states signals/transcription/some annotations are CC BY 4.0; attribution required, commercial use permitted. | Headset/lapel audio, orthographic time-synchronized word-level NXT transcript, channels/speakers; dialogue-act subsets. | 25 ES2002a review candidates processed through frozen V5 STT; scenario domain and mixed-speaker audio remain limitations. | ACCEPTED; bounded pilot acquired and processed, pending review. |
| Google FLEURS `en_in` | Existing Cozy acquisition script names `google/fleurs`; [dataset card](https://huggingface.co/datasets/google/fleurs-r/blob/c621c0b7b569dcebcd50273a187a35d1a1fc895f/README.md) records CC BY 4.0 | CC BY 4.0; attribution required; commercial use permitted. The Cozy script's archive paths return HTTP 404 at pinned `google/fleurs` revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`. | Indian-English audio/transcripts; scripted benchmark speech, no repairs. | Supplemental accent and STT-reference alignment control only, after finding an authoritative current artifact route. | DEFERRED PENDING RETRIEVABLE RELEASE. |
| Switchboard 1 / NXT annotations | [Switchboard catalog](https://catalog.ldc.upenn.edu/LDC93S8); [NXT](https://catalog.ldc.upenn.edu/LDC2009T26) | Base audio requires LDC agreement; NXT is CC BY-NC-SA 3.0 for non-profit access with separate for-profit terms. | Spontaneous telephone conversations; rich NXT layers. | Excellent research reference, but paid/restricted/non-commercial terms block product dataset use. | REJECTED. |
| FluencyBank / Timestamped | [access](https://talkbank.org/fluency/); [TalkBank rules](https://talkbank.org/0share/rules.html) | Much material needs approved/password access; default CC BY-NC-SA 3.0; rules prohibit inclusion in commercial products/models. | Audio/video, CHAT disfluency coding, timestamped derivative. | Valuable analysis source, incompatible with deployable V6 corpus. | REJECTED. |
| Local `cv_indian_full` | 3,987 rows in Cozy local manifest; builder cites `kaushalgawri/indian_accent_en_train` without retaining commit/license | Upstream version/license and redistribution terms are absent locally, so commercial status is unverified. | Scripted Common-Voice-style audio/text, age/gender/votes; no repair labels/timings/stable speakers. | Could be real-derived only after exact source license is recovered and targets reviewed. | REJECTED PENDING LICENSE PROOF. |
| Local `santhosh_indian` | 50 rows in Cozy local manifest; source builder has no retained license/version | Unverified. | Audio/text, no documented repair/timing/speaker fields. | Insufficient provenance. | REJECTED PENDING LICENSE PROOF. |
| AI4Bharat/IndicVoices Hindi | [Hugging Face dataset](https://huggingface.co/datasets/ai4bharat/IndicVoices) revision `c96f9088f138cf89d419da7e8e643e1f05c00a87` | CC BY 4.0; attribution required and commercial use permitted by the license. The repository is gated (`auto`), requiring access-condition acceptance/contact sharing before files can be fetched. | Hindi audio/text with verbatim and normalized transcripts, speaker ID, scenario/task, demographics, and duration; no verified word timestamps, repair labels, or English configuration. | Supplementary Hindi/Indic control data after target-STT and review; not evidence of Hinglish/code-switching coverage. | ACCEPTED WITH ACCESS GATE. |
| MUCS 2021 Hindi-English (OpenSLR SLR104) | [OpenSLR SLR104](https://openslr.org/104/) | CC BY-SA 4.0. Commercial use may be possible under the license, but share-alike implications for a distributed product/model need a project legal decision before ingestion. | 89.86 h train + 5.18 h test, 16 kHz audio/transcripts, sentence timestamps in baseline segments; technical spoken-tutorial domain. | High-value genuine Hindi-English technical code switching, but not conversational repair coverage. | DEFERRED PENDING LICENSE DECISION. |
| HiACC Hinglish adult/child corpus | [HiACC data paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC12329218/) / Zenodo `10.5281/zenodo.15551669` | The authoritative data-access statement says CC BY-NC 4.0 for academic/research use; the article's CC BY publication license does not change the dataset license. | 5.24 h / 5,176 16 kHz audio segments, adult and child read/spontaneous Hinglish with transcripts and splits; no verified word timestamps. | Valuable spontaneous code-switching and consent evidence, but non-commercial data terms block product-model training. | REJECTED. |
| OpenStax *Elementary Algebra 2e* | [Official title page](https://openstax.org/books/elementary-algebra-2e/pages/preface) / older PDF | The current official title page says CC BY-NC-SA 4.0 and prohibits LLM/generative-AI ingestion without permission; an older PDF carries a conflicting CC BY 4.0 notice. | English clean instructional prose, equations, symbols, headings, and tables; no audio, dialogue, repairs, or speaker metadata. | Potential math/technical clean-text source, but contradictory/current restrictive terms prevent use. | REJECTED PENDING WRITTEN PERMISSION. |
| People’s Speech | [project paper](https://arxiv.org/abs/2111.09344) | Mixture of CC BY-SA and CC BY sources; source-level obligations need review. | Large English ASR data with external provenance. | Scale is attractive, but heterogeneous licensing and weak repair labels make it unsafe for first ingestion. | REJECTED PENDING SOURCE-LEVEL REVIEW. |
| Formatting/technical seed | Organization-authored material only | No third-party text imported. | No audio unless separately synthesized and labelled synthetic. | Covers intentional structure, technical terms, quoted speech and metalinguistic negatives. | ACCEPTED as synthetic candidates with human review. |

## Acquisition rules

Before downloading an accepted source: pin URL/revision/date, preserve its
license or authoritative URL in the non-Git provenance workspace, record
attribution and resource estimate, and keep audio/caches outside Git. A
real-derived row requires source reference, actual target-STT backend/model and
authentic metadata, reference transcript, reviewed target, and a speaker or
source group. Discovered sources are never counted as examples.

## Candidate detail ledger

This ledger supplies the fields that are not compact enough for the summary
table. “Not stated” is intentional: it is not replaced with an estimate.

### Common Voice Spontaneous Speech English

- **Version/date:** Spontaneous Speech 3.0; catalog and terms checked
  2026-09-23. The English dataset ID is `cmn1pv5hi00uto1072y1074y7`.
  **Authority:** Mozilla Data Collective catalog/dataset page and Common Voice
  legal terms linked above.
- **Language/accent/domain:** English; crowd-contributed spontaneous responses;
  accent balance and speaker count are package metadata to preserve at ingest.
- **Scale/audio:** catalog lists 459.05 MB English MP3 ASR package; exact row
  count/hours not stated in the catalog result used for this audit.
- **Transcript/annotations/timing:** ASR transcripts; no verified repair,
  reparandum, word-timing, confidence, or alternatives annotation claim.
- **Terms:** CC0-1.0, commercial training permitted; no public mirror outside
  MDC. The official API documentation states that downloads require API
  credentials and acceptance of the dataset terms. **Decision:** ACCEPTED
  because source terms are explicit, but acquisition is blocked until an
  authorized MDC credential is available; a release record is still required
  before download.

### Common Voice Scripted English / Indian accent

- **Version/date:** exact release not yet selected; terms effective
  2025-10-31 were checked 2026-09-23. **Authority:** Common Voice legal terms.
- **Language/accent/domain:** English; a future Indian-accent subset must carry
  its own release metadata. Prompted/scripted, not conversational speech.
- **Scale/audio:** unknown until an exact release/subset is selected; audio and
  written prompts are expected but no local package exists.
- **Transcript/annotations/timing:** source prompt/validated transcript;
  no verified repair or word-timing labels. **Terms:** CC0 unless otherwise
  specified; commercial use allowed; no mirroring. **Decision:** ACCEPTED only
  as supplemental STT/reference evidence, not formatter gold labels.

### AMI Meeting Corpus

- **Version/date:** corpus download page; manual annotations v1.6.2 dated
  2017-04-10. **Authority:** AMI corpus/download/transcription pages.
- **Language/accent/domain:** English multiparty meetings; mainly elicited
  design-team scenarios with naturally occurring meeting remainder; mixed
  speaker backgrounds rather than Indian-English specific.
- **Scale/audio:** 100 hours; individual headset/lapel WAV and other channels
  are available. **Transcript/annotations/timing:** quality-controlled
  orthographic, time-synchronized word-level NXT transcription with channel and
  speaker information; dialogue-act and other phenomena on subsets.
- **Terms:** CC BY 4.0 signals/transcription/some annotations; attribution and
  redistribution-license compliance required; commercial use permitted.
  **Decision:** ACCEPTED for a bounded pilot, retaining attribution/release
  evidence and keeping audio outside Git.

### Google FLEURS `en_in`

- **Version/date:** `google/fleurs` is named by the existing acquisition script;
  its currently cached/pinned revision is
  `70bb2e84b976b7e960aa89f1c648e09c59f894dd`. The cited `google/fleurs-r`
  card records CC BY 4.0 and was checked 2026-09-23.
- **Language/accent/domain:** Indian English benchmark prompts. **Scale/audio:**
  audio plus train/dev/test TSV references are supported by the existing script;
  no local files/hours were found. **Transcript/annotations/timing:** scripted
  transcripts; no verified repair, speaker, or word-time labels.
- **Terms:** CC BY 4.0, attribution required, commercial use allowed. At the
  pinned `google/fleurs` revision, metadata-only requests for each expected
  `data/en_in/audio/{train,dev,test}.tar.gz` and TSV path returned HTTP 404;
  no file was downloaded. **Decision:** DEFERRED PENDING RETRIEVABLE RELEASE.
  Do not run the stale Cozy downloader or count any FLEURS row until an
  authoritative current artifact route and release record are captured.

### Switchboard and NXT Switchboard annotations

- **Version/date:** Switchboard Credit Card LDC93S8 (1993); NXT Switchboard
  Annotations LDC2009T26. **Language/domain:** US English spontaneous telephone
  conversations. **Scale/audio:** Credit Card subset is about eight hours;
  full Switchboard is described by LDC as about 2,400 two-sided conversations
  from 543 speakers. Audio exists.
- **Transcript/annotations/timing:** NXT combines multiple transcript
  annotation layers, suitable for discourse/disfluency research. **Terms:**
  base audio requires LDC agreement; NXT non-member access is CC BY-NC-SA 3.0.
  **Decision:** REJECTED for product training and redistribution constraints.

### FluencyBank / FluencyBank Timestamped

- **Version/date:** current TalkBank/FluencyBank access and rules checked
  2026-09-23. **Language/domain:** English speech including fluency-disorder,
  second-language, and control populations. **Scale:** no aggregate figure is
  asserted; access varies by corpus. Audio/video and CHAT-format transcript
  data exist; timestamped derivatives cover some material.
- **Terms:** approved/password access for much data; CC BY-NC-SA 3.0 default,
  with rules prohibiting model/product incorporation. **Decision:** REJECTED.

### Existing Cozy Indian-English assets

- **Version/date:** local manifests only: 3,987 `cv_indian_full` rows and 50
  `santhosh_indian` rows inspected 2026-09-23. **Language/domain:** Indian
  English, mostly scripted clips. **Audio/transcript:** local WAV plus text;
  `cv_indian_full` retains vote/age/gender metadata but no stable speaker ID,
  timing, repair annotation, or upstream revision/license snapshot.
- **Terms/commercial/redistribution:** unknown from retained evidence.
  **Decision:** REJECTED PENDING LICENSE PROOF; no records are admitted.

### IndicVoices, People’s Speech, and organization-authored synthetic text

- **IndicVoices:** Hugging Face dataset `ai4bharat/IndicVoices`, revision
  `c96f9088f138cf89d419da7e8e643e1f05c00a87`, declares CC BY 4.0 and gated
  (`auto`) file access. It has 22 declared Indian-language configurations,
  including Hindi but not English. Its Hindi schema declares audio path, text,
  duration, verbatim/normalized transcripts, speaker ID, scenario/task, and
  demographic/location fields. The source describes natural and spontaneous
  Indian speech, but this audit has no evidence that its Hindi rows contain
  usable English code-switching; it also has no verified word-time or repair
  annotations. **Decision:** ACCEPTED WITH ACCESS GATE for supplemental Hindi
  controls only. Do not label it Hinglish, download it, or admit rows until the
  access terms are accepted and a bounded release record is captured.
- **MUCS 2021 Hindi-English / OpenSLR SLR104:** OpenSLR identifies the
  authoritative resource as `SLR104`, under CC BY-SA 4.0. It publishes a 7.3
  GiB Hindi-English training archive plus a 443 MiB test archive, totaling
  89.86 and 5.18 hours respectively. Audio is 16 kHz/16-bit; the baseline
  segments carry sentence timestamps aligned to provided transcripts. The
  source is spoken technical tutorials, so it contributes real Hinglish and
  technical vocabulary but not the desired spontaneous conversational repair
  behavior. A third-party Hugging Face conversion labels itself CC BY 4.0, but
  that is not used as the license authority because OpenSLR specifies CC BY-SA
  4.0. **Decision:** DEFERRED PENDING LICENSE DECISION. Do not download or
  admit it until the project determines whether the CC BY-SA obligations fit
  all planned model/product distribution paths.
- **HiACC Hinglish adult/child corpus:** The 2025 data paper identifies Zenodo
  record `10.5281/zenodo.15551669` and says its data are open for
  academic/research use under CC BY-NC 4.0. It contains 3,318 adult plus 1,858
  child 16 kHz segments (5.24 hours total), including read and spontaneous
  Hindi-English code-switching, with transcript/split annotations. The paper
  documents participant consent and ethics approval, but that does not replace
  the non-commercial license restriction. The paper itself is CC BY 4.0, which
  is a publication license rather than evidence that the data are CC BY.
  **Decision:** REJECTED for deployable V6 training and redistribution. Do not
  download or count rows unless the data owners provide a separate compatible
  license.
- **OpenStax *Elementary Algebra 2e*:** This title was initially considered for
  clean English mathematical/technical sentences, equations, headings, tables,
  capitalization, and punctuation. The title’s older PDF shows a CC BY 4.0
  notice, but the current official title page states CC BY-NC-SA 4.0 and says
  the book may not be ingested into LLM or generative-AI offerings without
  OpenStax permission. The publication date shown there is 2020-04-22. It has
  no speech, speaker, disfluency, repair, or timing evidence in any case.
  **Decision:** REJECTED PENDING WRITTEN PERMISSION. The current restrictive
  title-page terms govern this audit; do not download, transform, or count text
  from it for V6 despite the older PDF notice.
- **People’s Speech:** English, large multi-source ASR; the cited paper reports
  mixed CC BY-SA/CC BY provenance. Exact audio/transcript/timing availability
  is source-dependent. **Decision:** REJECTED PENDING SOURCE-LEVEL REVIEW.
- **Organization-authored seed:** 48 synthetic text candidates, no audio,
  generated 2026-09-23. License is organization-authored; commercial and
  redistribution use is under project control. **Decision:** ACCEPTED only as
  `needs_human_review` synthetic candidates, never real speech.
