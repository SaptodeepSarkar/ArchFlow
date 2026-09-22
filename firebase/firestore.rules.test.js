const assert = require('node:assert/strict');
const {
  initializeTestEnvironment,
  assertFails,
  assertSucceeds,
} = require('@firebase/rules-unit-testing');
const { doc, getDoc, setDoc, deleteDoc } = require('firebase/firestore');

let env;

const encryptedRecord = {
  schema_version: 1,
  record_id: 'hyprland',
  updated_at_ms: 1000,
  compression: 'gzip',
  cipher: 'aes-256-gcm',
  nonce: 'abcdefghijklmnop',
  ciphertext: 'this-is-an-encrypted-payload-not-a-vocabulary-word',
};

before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'vaani-rules-test',
    firestore: { rules: require('node:fs').readFileSync('../firestore.rules', 'utf8') },
  });
});

after(async () => env && env.cleanup());

function aliceDb() { return env.authenticatedContext('alice').firestore(); }
function bobDb() { return env.authenticatedContext('bob').firestore(); }
function anonymousDb() { return env.unauthenticatedContext().firestore(); }

describe('Vaani Firestore privacy boundary', () => {
  it('allows an authenticated owner to write and read personalization', async () => {
    const ref = doc(aliceDb(), 'users/alice/personalization/hyprland');
    await assertSucceeds(setDoc(ref, encryptedRecord));
    await assertSucceeds(getDoc(ref));
  });

  it('denies unauthenticated and cross-user access', async () => {
    await assertFails(getDoc(doc(anonymousDb(), 'users/alice/personalization/hyprland')));
    await assertFails(getDoc(doc(bobDb(), 'users/alice/personalization/hyprland')));
  });

  it('denies hard deletes, plaintext records, and raw dictation paths', async () => {
    const ref = doc(aliceDb(), 'users/alice/personalization/hyprland');
    await assertSucceeds(setDoc(ref, encryptedRecord));
    await assertFails(deleteDoc(ref));
    await assertFails(setDoc(ref, { ...encryptedRecord, value: { canonical: 'plain text' } }));
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/audio/raw'), { bytes: 'never' }));
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/dictations/raw'), { text: 'never' }));
  });

  it('rejects unknown fields and records owned by another user', async () => {
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/personalization/bad'), { ...encryptedRecord, unexpected: true }));
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/personalization/other'), { ...encryptedRecord, record_id: 'other' }));
  });
});
