package org.vaani.app

import android.app.Activity
import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import kotlinx.coroutines.tasks.await

data class VaaniAccount(val uid: String, val label: String, val provider: String)

/**
 * Firebase identity boundary. It deliberately stores no password, token, audio,
 * or dictation text; Firebase Auth owns credentials and refresh tokens.
 */
class VaaniAccountClient(private val context: Context) {
    private val auth = FirebaseAuth.getInstance()

    fun current(): VaaniAccount? = auth.currentUser?.let { user ->
        val provider = user.providerData.lastOrNull()?.providerId ?: "firebase"
        VaaniAccount(user.uid, user.email ?: "Signed in", provider)
    }

    suspend fun signUp(email: String, password: String): Result<VaaniAccount> = runCatching {
        require(email.isNotBlank() && password.length >= 8) { "Use an email and a password with at least 8 characters." }
        auth.createUserWithEmailAndPassword(email.trim(), password).await()
        current() ?: error("Your account could not be opened.")
    }

    suspend fun signIn(email: String, password: String): Result<VaaniAccount> = runCatching {
        require(email.isNotBlank() && password.isNotBlank()) { "Enter your email and password." }
        auth.signInWithEmailAndPassword(email.trim(), password).await()
        current() ?: error("Your account could not be opened.")
    }

    suspend fun signInWithGoogle(activity: Activity): Result<VaaniAccount> = runCatching {
        val resource = context.resources.getIdentifier("default_web_client_id", "string", context.packageName)
        check(resource != 0) { "Google sign-in is being prepared. Update the Firebase Android configuration first." }
        val option = GetGoogleIdOption.Builder()
            .setServerClientId(context.getString(resource))
            .setFilterByAuthorizedAccounts(false)
            .setAutoSelectEnabled(true)
            .build()
        val result = CredentialManager.create(context).getCredential(
            activity,
            GetCredentialRequest.Builder().addCredentialOption(option).build(),
        )
        val credential = result.credential as? CustomCredential
            ?: error("Google did not return an account.")
        check(credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            "Google did not return an ID token."
        }
        val token = GoogleIdTokenCredential.createFrom(credential.data).idToken
        auth.signInWithCredential(GoogleAuthProvider.getCredential(token, null)).await()
        current() ?: error("Your Google account could not be opened.")
    }

    fun signOut() = auth.signOut()
}
