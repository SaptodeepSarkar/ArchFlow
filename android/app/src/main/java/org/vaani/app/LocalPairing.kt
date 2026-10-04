package org.vaani.app

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.json.JSONObject
import org.json.JSONArray
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.SocketTimeoutException
import java.math.BigInteger
import java.security.*
import java.security.cert.X509Certificate
import java.util.Date
import javax.net.ssl.*
import kotlin.coroutines.coroutineContext

/** TLS 1.3 pinned to the invitation certificate. No listeners exist outside Receive. */
class LocalPairing : AutoCloseable {
    @Volatile private var server: SSLServerSocket? = null
    @Volatile private var connected: SSLSocket? = null
    @Volatile private var cancelled = false
    data class Invitation(val host: String,val port: Int,val fingerprint: String,val token: String,val expires: Long) {
        fun encode(): String = "VAANI1-"+Base64.encodeToString(JSONObject().put("v",1).put("host",host).put("port",port).put("cert_sha256",fingerprint).put("token",token).put("expires_at_ms",expires).toString().toByteArray(),Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }
    fun prepare(host: String): Invitation {
        check(server==null);cancelled=false
        require(isLocal(host)) { "Choose a local-network IPv4 address" }
        val pair=KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
        val name=X500Name("CN=Vaani local pairing");val now=System.currentTimeMillis()
        val certificate=JcaX509CertificateConverter().setProvider(BouncyCastleProvider()).getCertificate(
            JcaX509v3CertificateBuilder(name,BigInteger(128,SecureRandom()),Date(now-60_000),Date(now+86_400_000),name,pair.public)
                .build(JcaContentSignerBuilder("SHA256withRSA").setProvider(BouncyCastleProvider()).build(pair.private)))
        val keys=KeyStore.getInstance(KeyStore.getDefaultType()).apply {load(null);setKeyEntry("pair",pair.private,CharArray(0),arrayOf(certificate))}
        val managers=KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm()).apply {init(keys,CharArray(0))}
        val context=SSLContext.getInstance("TLSv1.3").apply {init(managers.keyManagers,null,SecureRandom())}
        val socket=context.serverSocketFactory.createServerSocket(0,1,InetAddress.getByName(host)) as SSLServerSocket
        socket.enabledProtocols=arrayOf("TLSv1.3");socket.soTimeout=500;server=socket
        val token=Base64.encodeToString(ByteArray(32).also(SecureRandom()::nextBytes),Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        return Invitation(host,socket.localPort,digest(certificate.encoded),token,now+120_000)
    }
    suspend fun receive(invitation: Invitation): JSONObject = withContext(Dispatchers.IO) {
        try {
            while(!cancelled && System.currentTimeMillis()<invitation.expires) {
                coroutineContext.ensureActive()
                val socket=try {server!!.accept() as SSLSocket} catch(_:SocketTimeoutException){continue}
                connected=socket
                socket.use {
                    it.soTimeout=10_000;it.enabledProtocols=arrayOf("TLSv1.3");it.startHandshake()
                    val packet=JSONObject(readFrame(it))
                    check(System.currentTimeMillis()<invitation.expires && MessageDigest.isEqual(packet.getString("token").toByteArray(),invitation.token.toByteArray())) {"Invitation expired or authentication failed"}
                    val bundle=packet.getJSONObject("bundle");validateBundle(bundle)
                    writeFrame(it,"{\"status\":\"pending_receiver_approval\"}")
                    return@withContext bundle
                }
            }
            error("Receive session expired or cancelled")
        } finally { close() }
    }
    suspend fun send(invitationText: String,bundle: JSONObject) = withContext(Dispatchers.IO) {
        val invitation=parse(invitationText);validateBundle(bundle)
        val trust=object:X509TrustManager {
            override fun getAcceptedIssuers()=emptyArray<X509Certificate>()
            override fun checkClientTrusted(chain:Array<X509Certificate>,authType:String)=error("Not a receiving context")
            override fun checkServerTrusted(chain:Array<X509Certificate>,authType:String){check(chain.isNotEmpty()&&digest(chain[0].encoded)==invitation.fingerprint){"Peer certificate does not match the scanned invitation"}}
        }
        val context=SSLContext.getInstance("TLSv1.3").apply {init(null,arrayOf(trust),SecureRandom())}
        val socket=context.socketFactory.createSocket() as SSLSocket;connected=socket
        try {socket.use {
            it.connect(java.net.InetSocketAddress(invitation.host,invitation.port),5_000);it.soTimeout=10_000;it.enabledProtocols=arrayOf("TLSv1.3");it.startHandshake();coroutineContext.ensureActive()
            writeFrame(it,JSONObject().put("token",invitation.token).put("bundle",bundle).toString())
            check(JSONObject(readFrame(it)).getString("status")=="pending_receiver_approval")
        }} finally {close()}
    }
    override fun close(){cancelled=true;connected?.runCatching {close()};connected=null;server?.runCatching {close()};server=null}
    companion object {
        const val MAX_BYTES=900_000
        fun addresses(): List<String> = NetworkInterface.getNetworkInterfaces().toList().flatMap { it.inetAddresses.toList() }.filter {it is java.net.Inet4Address && it.isSiteLocalAddress}.map {it.hostAddress!!}
        private fun isLocal(host: String): Boolean = host.matches(Regex("[0-9.]+")) && InetAddress.getByName(host).let {it is java.net.Inet4Address && (it.isSiteLocalAddress||it.isLoopbackAddress||it.isLinkLocalAddress)}
        fun parse(text: String): Invitation {
            require(text.length<4096 && text.trim().startsWith("VAANI1-"))
            val json=JSONObject(String(Base64.decode(text.trim().removePrefix("VAANI1-"),Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)))
            val result=Invitation(json.getString("host"),json.getInt("port"),json.getString("cert_sha256"),json.getString("token"),json.getLong("expires_at_ms"))
            require(json.getInt("v")==1 && isLocal(result.host)&&result.port in 1..65535&&result.fingerprint.matches(Regex("[0-9a-f]{64}"))&&result.token.length==43&&result.expires>System.currentTimeMillis()&&result.expires<=System.currentTimeMillis()+310_000)
            return result
        }
        fun validateBundle(bundle: JSONObject) {
            require(bundle.getInt("schema_version")==1&&bundle.toString().toByteArray().size<=MAX_BYTES)
            val records=bundle.getJSONArray("records");require(records.length()<=2000)
            for(i in 0 until records.length()) {
                val record=records.getJSONObject(i);val names=record.keys().asSequence().toList();require(names.size==1&&names[0] in setOf("Vocabulary","Snippet","Replacement"))
                val body=record.getJSONObject(names[0]);val id=body.getString("id");require(id.isNotEmpty()&&id.length<=128&&body.getInt("schema_version")==1&&body.getString("entity")==names[0].lowercase()&&body.getString("writer_device_id").length<=128&&record.toString().toByteArray().size<=64*1024)
                if(!body.isNull("value")) require(body.getJSONObject("value").getString("id")==id)
            }
            val preferences=bundle.optJSONObject("preferences") ?: return
            preferences.keys().forEach {key ->val value=preferences.getString(key);require(when(key){"recognition.language"->value in setOf("en","hi","bn");"general.residency_profile"->value in setOf("economy","balanced","ready");"recognition.server_idle_secs"->value.toLong() in 0..600;else->false})}
        }
        fun bundle(context: android.content.Context,includePreferences: Boolean): JSONObject {
            val store=PersonalizationStore(context)
            return JSONObject().put("schema_version",1).put("records",JSONArray(store.syncRecords(store.deviceId()))).put("preferences",if(includePreferences) JSONObject(AppSettings.portable(context)) else JSONObject())
        }
        private fun digest(bytes: ByteArray)=MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
        private fun readFrame(socket: SSLSocket): String {val input=DataInputStream(socket.inputStream);val n=input.readInt();require(n in 1..MAX_BYTES);val bytes=ByteArray(n);input.readFully(bytes);return String(bytes,Charsets.UTF_8)}
        private fun writeFrame(socket: SSLSocket,text:String){val bytes=text.toByteArray(Charsets.UTF_8);require(bytes.size<=MAX_BYTES);DataOutputStream(socket.outputStream).apply {writeInt(bytes.size);write(bytes);flush()}}
    }
}
