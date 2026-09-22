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
edit schedules one bounded sync, while an opaque FCM `sync_available` wakeup
schedules a single WorkManager pull. Neither carries vocabulary, links, or
dictation text. Android and desktop share the envelope, record JSON, and
deterministic `(logical clock, writer ID, revision, updated time)` merge rule.

The rules in [`firestore.rules`](../../firestore.rules) enforce:

- authentication and same-user reads/writes;
- the allow-listed encrypted envelope only; plaintext record fields are denied;
- stable document IDs and monotonic encrypted-envelope update times;
- no hard deletes for personalization records;
- no storage path for audio, raw dictations, tokens, or arbitrary documents.

The repository binds its Firebase CLI default to the existing `arch-flow-vanni`
development project in `.firebaserc`; no credentials are committed. The
Android client uses the registered `google-services.json` configuration and
does not make sign-in mandatory. Its Home-menu account surface supports
email/password and Google identity. The Android debug SHA-1 is registered for
emulator builds, but a refreshed configuration still needs a generated
`default_web_client_id` before Google sign-in can complete.

As checked on 2026-09-22, Firebase Authentication has not been initialized in
this project and Google's management API reports `BILLING_NOT_ENABLED` for
that initialization. Do not enable billing or choose a Cloud Firestore region
from an automated repository task: both are an operator decision with cost and
data-residency consequences. Once an operator has enabled billing, initialize
Firebase Authentication, enable Email/Password and Google, refresh
`android/app/google-services.json`, select the Firestore region, and deploy
the rules. Validate the rules with the Firebase Emulator Suite before that
operator-approved deploy:

```sh
cd firebase
npm install
firebase emulators:exec --only firestore "npm test"
cd ..
firebase deploy --only firestore:rules,firestore:indexes,functions
```

Deployment is intentionally not attempted by the repository build. The core
`SyncProvider` contract, local JSONL implementation, Android auth client/provider,
and a desktop Firestore REST provider plus email/password Auth client are
source-implemented. The desktop provider uses the same recovery-code envelope
and its OS credential store; Android uses Android Keystore for its local copy.
Firebase Cloud Functions sends only an opaque FCM wakeup after an encrypted
record changes. Deploying that function requires an operator-approved Firebase
billing plan, so it is deliberately not done by repository builds.
