#!/usr/bin/env bash
set -euo pipefail

# Spark has Firestore, Authentication, and FCM, but not Cloud Functions.
# Deploy only the services that are available without enabling billing.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

command -v firebase >/dev/null || {
  echo "firebase CLI is required: npm install -g firebase-tools" >&2
  exit 1
}

echo "Deploying Spark-compatible Firestore rules and indexes..."
firebase deploy --only firestore:rules,firestore:indexes
echo
echo "Done. Cloud Functions were not deployed because Spark does not support them."
echo "Android sync remains local-first and syncs on sign-in, app resume, and edits."
