const assert = require('node:assert/strict');
const {
  initializeTestEnvironment,
  assertFails,
  assertSucceeds,
} = require('@firebase/rules-unit-testing');
const { doc, getDoc, setDoc, deleteDoc } = require('firebase/firestore');

let env;

const vocabulary = {
  schema_version: 1,
  entity: 'vocabulary',
  id: 'hyprland',
  revision: 1,
  logical_clock: 1,
  writer_device_id: 'android-test',
  updated_at_ms: 1000,
  deleted_at_ms: null,
  value: {
    id: 'hyprland',
    canonical: 'Hyprland',
    spoken_aliases: ['hyperland'],
    category: null,
    created_at_ms: 1000,
    updated_at_ms: 1000,
  },
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
    await assertSucceeds(setDoc(ref, vocabulary));
    await assertSucceeds(getDoc(ref));
  });

  it('denies unauthenticated and cross-user access', async () => {
    await assertFails(getDoc(doc(anonymousDb(), 'users/alice/personalization/hyprland')));
    await assertFails(getDoc(doc(bobDb(), 'users/alice/personalization/hyprland')));
  });

  it('allows tombstones but denies hard deletes and raw dictation paths', async () => {
    const ref = doc(aliceDb(), 'users/alice/personalization/hyprland');
    const tombstone = { ...vocabulary, revision: 2, logical_clock: 2, deleted_at_ms: 2000, value: null };
    await assertSucceeds(setDoc(ref, tombstone));
    await assertFails(deleteDoc(ref));
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/audio/raw'), { bytes: 'never' }));
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/dictations/raw'), { text: 'never' }));
  });

  it('rejects unknown fields and records owned by another user', async () => {
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/personalization/bad'), { ...vocabulary, unexpected: true }));
    await assertFails(setDoc(doc(aliceDb(), 'users/alice/personalization/other'), { ...vocabulary, id: 'other' }));
  });
});
