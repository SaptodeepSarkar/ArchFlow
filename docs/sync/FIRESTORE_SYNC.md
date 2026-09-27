# Firestore sync surface

Vaani sync is optional and local-first. Dictation does not wait for a cloud
connection. The initial cloud surface is deliberately narrow:

`/users/{uid}/personalization/{recordId}`

Only vocabulary, snippet, and replacement records are eligible. Each record is
serialized as versioned `vaani-core` JSON, gzip-compressed, then encrypted with
AES-256-GCM on the device. Firestore receives only its record ID, update time,
nonce, and ciphertext. A 256-bit recovery code is generated on a first device
and explicitly added to other devices; it is protected at rest by each
platform's secure store and is never derived from an account password.

The local repository remains the source of immediate behavior. An Android local
edit schedules one bounded sync, and the app pulls once on sign-in and resume.
On Blaze, an opaque FCM `sync_available` wakeup additionally schedules a single
WorkManager pull. On Spark, Cloud Functions are unavailable, so background
push-triggered sync is not possible; no plaintext workaround or polling loop is
introduced. Android and desktop share the envelope, record JSON, and
deterministic `(logical clock, writer ID, revision, updated time)` merge rule.

The rules in [`firestore.rules`](../../firestore.rules) enforce:

- authentication and same-user reads/writes;
- the allow-listed encrypted envelope only; plaintext record fields are denied;
- stable document IDs and monotonic encrypted-envelope update times;
- no hard deletes for personalization records;
- no storage path for audio, raw dictations, tokens, or arbitrary documents.

The repository binds its Firebase CLI default to the existing `arch-flow-vanni`
development project in `.firebaserc`; no credentials are committed. The
Android client uses Firebase only when a local `google-services.json` is
provided, and does not make sign-in mandatory. Its Home-menu account surface
supports email/password and Google identity.

Deployment audit, 2026-09-27: the active project has a native default
Firestore database in `asia-south2` (created 2026-09-22) and one active
Android app (`org.vaani.keyboard`). The CLI reports **no deployed Cloud
Functions**, so the source's opaque FCM wake-up function is not live and
cross-device background notification sync is not currently available. The
repository cannot prove the deployed Firestore rules or Authentication provider
configuration from its checked-in files; source rules are not deployment
evidence. Therefore real account sync must be treated as unavailable until an
operator verifies Auth providers, deploys the reviewed rules, and performs a
two-device recovery-code test. Do not enable billing or alter the database
region from an automated repository task.

Before an operator-approved deploy, validate the rules with the Firebase
Emulator Suite:

```sh
cd firebase
npm install
firebase emulators:exec --only firestore "npm test"
cd ..
./firebase/deploy-spark.sh
```

Deployment is intentionally not attempted by the repository build. The core
`SyncProvider` contract, local JSONL implementation, Android auth client/provider,
and a desktop Firestore REST provider plus email/password Auth client are
source-implemented. The desktop provider uses the same recovery-code envelope
and its OS credential store; Android uses Android Keystore for its local copy.
Firebase Cloud Functions sends only an opaque FCM wakeup after an encrypted
record changes when the project is on Blaze. The Spark-safe deploy script skips
that service and deploys rules/indexes only. Firebase documents that Cloud
Functions deployment requires Blaze; Firestore, Authentication, and FCM remain
available under Spark. See [Firebase pricing](https://firebase.google.com/pricing)
and [Cloud Functions quotas](https://firebase.google.com/docs/functions/quotas).
