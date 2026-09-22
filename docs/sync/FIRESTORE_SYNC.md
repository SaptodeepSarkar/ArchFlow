# Firestore sync surface

Vaani sync is optional and local-first. Dictation does not wait for a cloud
connection. The initial cloud surface is deliberately narrow:

`/users/{uid}/personalization/{recordId}`

Only vocabulary, snippet, and replacement records are eligible. Each record
uses the versioned `vaani-core` envelope: schema version, stable record ID,
revision, Lamport-style logical clock, writer device ID, update time, and an
optional value or deletion tombstone. The local repository remains the source
of immediate behavior; the Android Firebase provider pushes/pulls records after
optional sign-in through a bounded, network-constrained periodic WorkManager
job, and also exposes an explicit sync action. It applies the same deterministic
merge policy in both paths. The Linux/Windows provider adapters remain to be
connected.

The rules in [`firestore.rules`](../../firestore.rules) enforce:

- authentication and same-user reads/writes;
- an allow-listed envelope and entity-specific value shape;
- stable IDs, bounded text, non-negative revisions/clocks, and monotonic
  updates;
- tombstone-only deletion, with no hard deletes;
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
firebase deploy --only firestore:rules,firestore:indexes
```

Deployment is intentionally not attempted by the repository build. The core
`SyncProvider` contract, local JSONL implementation, Android auth client/provider,
and a desktop Firestore REST provider plus email/password Auth client are
source-implemented. Desktop tokens remain memory-only in the shared client; the
desktop provider accepts an injected Firebase ID-token supplier so Linux and
Windows can bind it to OS-secure credential storage. `DesktopSyncClient` provides
the local-first sign-in/sync lifecycle, and `SecureSessionStore` implements the
platform keyring binding. Desktop sign-in UI and runtime keyring availability
checks still require environment-specific shell work.
