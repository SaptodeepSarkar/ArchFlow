const { onDocumentWritten } = require('firebase-functions/v2/firestore');
const { initializeApp } = require('firebase-admin/app');
const { getFirestore } = require('firebase-admin/firestore');
const { getMessaging } = require('firebase-admin/messaging');

initializeApp();

// Sends no user text—only an instruction for registered devices to perform
// their own authenticated, bounded encrypted pull.
exports.notifyEncryptedSync = onDocumentWritten('users/{uid}/personalization/{recordId}', async event => {
  if (!event.data?.after.exists) return;
  const devices = await getFirestore().collection('users').doc(event.params.uid).collection('devices').get();
  const tokens = devices.docs.map(doc => doc.get('push_token')).filter(token => typeof token === 'string' && token.length > 0);
  if (!tokens.length) return;
  await getMessaging().sendEachForMulticast({ tokens, data: { kind: 'sync_available' }, android: { priority: 'high' } });
});
