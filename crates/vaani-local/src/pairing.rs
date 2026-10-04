//! One-shot, explicit local-network transfer. Certificate pinning is the trust anchor.
use aes_gcm::aead::{rand_core::RngCore, OsRng};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use openssl::{
    asn1::Asn1Time,
    hash::MessageDigest,
    pkey::PKey,
    rsa::Rsa,
    ssl::{SslAcceptor, SslConnector, SslMethod, SslVerifyMode, SslVersion},
    x509::{X509NameBuilder, X509},
};
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    net::{IpAddr, TcpListener, TcpStream},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use vaani_core::sync::PersonalizationRecord;
pub const MAX_BYTES: usize = 900_000;
#[derive(Clone, Serialize, Deserialize)]
pub struct Invitation {
    pub v: u32,
    pub host: String,
    pub port: u16,
    pub cert_sha256: String,
    pub token: String,
    pub expires_at_ms: u64,
}
#[derive(Clone, Serialize, Deserialize, Default)]
pub struct Bundle {
    pub schema_version: u32,
    pub records: Vec<PersonalizationRecord>,
    #[serde(default)]
    pub preferences: std::collections::BTreeMap<String, String>,
}
#[derive(Serialize, Deserialize)]
struct Packet {
    token: String,
    bundle: Bundle,
}
fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
impl Invitation {
    pub fn encode(&self) -> anyhow::Result<String> {
        Ok(format!(
            "VAANI1-{}",
            URL_SAFE_NO_PAD.encode(serde_json::to_vec(self)?)
        ))
    }
    pub fn parse(text: &str) -> anyhow::Result<Self> {
        anyhow::ensure!(text.len() < 4096, "invitation too large");
        let this: Self = serde_json::from_slice(
            &URL_SAFE_NO_PAD.decode(
                text.trim()
                    .strip_prefix("VAANI1-")
                    .ok_or_else(|| anyhow::anyhow!("invalid invitation"))?,
            )?,
        )?;
        anyhow::ensure!(
            this.v == 1
                && this.port > 0
                && this.cert_sha256.len() == 64
                && this.token.len() == 43
                && this.expires_at_ms > now()
                && this.expires_at_ms <= now() + 310_000,
            "invalid or expired invitation"
        );
        let ip: IpAddr = this.host.parse()?;
        anyhow::ensure!(
            ip.is_loopback()
                || match ip {
                    IpAddr::V4(v) => v.is_private() || v.is_link_local(),
                    IpAddr::V6(v) => v.is_unique_local() || v.is_unicast_link_local(),
                },
            "Only local-network addresses are supported"
        );
        Ok(this)
    }
    pub fn qr_svg(&self) -> anyhow::Result<String> {
        Ok(qrcode::QrCode::new(self.encode()?)?
            .render::<qrcode::render::svg::Color>()
            .min_dimensions(240, 240)
            .build())
    }
}
impl Bundle {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            self.schema_version == 1
                && self.records.len() <= 2000
                && serde_json::to_vec(self)?.len() <= MAX_BYTES,
            "transfer limits exceeded"
        );
        for record in &self.records {
            anyhow::ensure!(
                !record.id().is_empty() && record.id().len() <= 128,
                "invalid record identity"
            );
            let data = serde_json::to_value(record)?;
            let body = data.as_object().unwrap().values().next().unwrap();
            anyhow::ensure!(body["schema_version"] == 1, "record schema");
            anyhow::ensure!(
                body["writer_device_id"]
                    .as_str()
                    .is_some_and(|v| v.len() <= 128),
                "record writer"
            );
            anyhow::ensure!(
                serde_json::to_vec(record)?.len() <= 64 * 1024,
                "record too large"
            );
            match record {
                PersonalizationRecord::Vocabulary(r) => anyhow::ensure!(
                    r.entity == vaani_core::sync::SyncEntityKind::Vocabulary,
                    "entity mismatch"
                ),
                PersonalizationRecord::Snippet(r) => anyhow::ensure!(
                    r.entity == vaani_core::sync::SyncEntityKind::Snippet,
                    "entity mismatch"
                ),
                PersonalizationRecord::Replacement(r) => anyhow::ensure!(
                    r.entity == vaani_core::sync::SyncEntityKind::Replacement,
                    "entity mismatch"
                ),
            };
        }
        for (key, value) in &self.preferences {
            anyhow::ensure!(
                matches!(
                    key.as_str(),
                    "recognition.language"
                        | "general.residency_profile"
                        | "recognition.server_idle_secs"
                ),
                "nonportable preference"
            );
            let mut cfg = vaani_core::config::Config::default();
            cfg.set_key(key, value).map_err(anyhow::Error::msg)?;
        }
        Ok(())
    }
}
fn frame_write<W: Write>(writer: &mut W, bytes: &[u8]) -> anyhow::Result<()> {
    anyhow::ensure!(bytes.len() <= MAX_BYTES, "frame too large");
    writer.write_all(&(bytes.len() as u32).to_be_bytes())?;
    writer.write_all(bytes)?;
    writer.flush()?;
    Ok(())
}
fn frame_read<R: Read>(reader: &mut R) -> anyhow::Result<Vec<u8>> {
    let mut length = [0; 4];
    reader.read_exact(&mut length)?;
    let n = u32::from_be_bytes(length) as usize;
    anyhow::ensure!(n > 0 && n <= MAX_BYTES, "frame too large");
    let mut bytes = vec![0; n];
    reader.read_exact(&mut bytes)?;
    Ok(bytes)
}
pub struct Receiver {
    listener: TcpListener,
    tls: SslAcceptor,
    pub invitation: Invitation,
}
impl Receiver {
    pub fn new(host: &str) -> anyhow::Result<Self> {
        let ip: IpAddr = host.parse()?;
        anyhow::ensure!(ip.is_ipv4(), "Use a local IPv4 address");
        let key = PKey::from_rsa(Rsa::generate(2048)?)?;
        let mut name = X509NameBuilder::new()?;
        name.append_entry_by_text("CN", "Vaani local pairing")?;
        let name = name.build();
        let mut certificate = X509::builder()?;
        certificate.set_version(2)?;
        certificate.set_subject_name(&name)?;
        certificate.set_issuer_name(&name)?;
        certificate.set_pubkey(&key)?;
        let start = Asn1Time::days_from_now(0)?;
        let end = Asn1Time::days_from_now(1)?;
        certificate.set_not_before(&start)?;
        certificate.set_not_after(&end)?;
        certificate.sign(&key, MessageDigest::sha256())?;
        let certificate = certificate.build();
        let mut tls = SslAcceptor::mozilla_modern_v5(SslMethod::tls())?;
        tls.set_min_proto_version(Some(SslVersion::TLS1_3))?;
        tls.set_private_key(&key)?;
        tls.set_certificate(&certificate)?;
        tls.check_private_key()?;
        let listener = TcpListener::bind((host, 0))?;
        listener.set_nonblocking(true)?;
        let mut token = [0; 32];
        OsRng.fill_bytes(&mut token);
        let invitation = Invitation {
            v: 1,
            host: host.into(),
            port: listener.local_addr()?.port(),
            cert_sha256: hex(&certificate.digest(MessageDigest::sha256())?),
            token: URL_SAFE_NO_PAD.encode(token),
            expires_at_ms: now() + 120_000,
        };
        Ok(Self {
            listener,
            tls: tls.build(),
            invitation,
        })
    }
    pub fn receive(self, cancel: &std::sync::atomic::AtomicBool) -> anyhow::Result<Bundle> {
        let deadline = self.invitation.expires_at_ms;
        while now() < deadline && !cancel.load(std::sync::atomic::Ordering::Relaxed) {
            match self.listener.accept() {
                Ok((stream, _)) => {
                    stream.set_read_timeout(Some(Duration::from_secs(10)))?;
                    stream.set_write_timeout(Some(Duration::from_secs(10)))?;
                    let result = (|| {
                        let mut stream = self
                            .tls
                            .accept(stream)
                            .map_err(|_| anyhow::anyhow!("TLS handshake failed"))?;
                        let packet: Packet = serde_json::from_slice(&frame_read(&mut stream)?)?;
                        anyhow::ensure!(
                            now() < deadline
                                && openssl::memcmp::eq(
                                    packet.token.as_bytes(),
                                    self.invitation.token.as_bytes()
                                ),
                            "Invitation expired or authentication failed"
                        );
                        packet.bundle.validate()?;
                        frame_write(&mut stream, b"{\"status\":\"pending_receiver_approval\"}")?;
                        Ok(packet.bundle)
                    })();
                    return result;
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(100))
                }
                Err(e) => return Err(e.into()),
            }
        }
        anyhow::bail!("Receive session expired or cancelled")
    }
}
pub fn send(invitation: &Invitation, bundle: &Bundle) -> anyhow::Result<()> {
    bundle.validate()?;
    Invitation::parse(&invitation.encode()?)?;
    let expected = invitation.cert_sha256.clone();
    let mut connector = SslConnector::builder(SslMethod::tls())?;
    connector.set_min_proto_version(Some(SslVersion::TLS1_3))?;
    connector.set_verify_callback(SslVerifyMode::PEER, move |_, context| {
        context.error_depth() == 0
            && context
                .current_cert()
                .and_then(|cert| cert.digest(MessageDigest::sha256()).ok())
                .is_some_and(|hash| hex(&hash) == expected)
    });
    let address = format!("{}:{}", invitation.host, invitation.port).parse()?;
    let socket = TcpStream::connect_timeout(&address, Duration::from_secs(5))?;
    socket.set_read_timeout(Some(Duration::from_secs(10)))?;
    socket.set_write_timeout(Some(Duration::from_secs(10)))?;
    let mut stream = connector
        .build()
        .configure()?
        .verify_hostname(false)
        .connect(&invitation.host, socket)
        .map_err(|_| anyhow::anyhow!("Peer certificate did not match the invitation"))?;
    frame_write(
        &mut stream,
        &serde_json::to_vec(&Packet {
            token: invitation.token.clone(),
            bundle: bundle.clone(),
        })?,
    )?;
    let response = frame_read(&mut stream)?;
    anyhow::ensure!(
        serde_json::from_slice::<serde_json::Value>(&response)?["status"]
            == "pending_receiver_approval",
        "Peer rejected transfer"
    );
    Ok(())
}
pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn loopback_pinned_tls_transfer_and_single_use() {
        let receiver = Receiver::new("127.0.0.1").unwrap();
        let invite = receiver.invitation.clone();
        let thread = std::thread::spawn(move || {
            receiver
                .receive(&std::sync::atomic::AtomicBool::new(false))
                .unwrap()
        });
        let bundle = Bundle {
            schema_version: 1,
            ..Default::default()
        };
        send(&invite, &bundle).unwrap();
        assert_eq!(thread.join().unwrap().schema_version, 1);
        assert!(send(&invite, &bundle).is_err());
    }
    #[test]
    fn wrong_certificate_pin_is_rejected() {
        let receiver = Receiver::new("127.0.0.1").unwrap();
        let mut invite = receiver.invitation.clone();
        invite.cert_sha256 = "00".repeat(32);
        let t = std::thread::spawn(move || {
            receiver.receive(&std::sync::atomic::AtomicBool::new(false))
        });
        assert!(send(
            &invite,
            &Bundle {
                schema_version: 1,
                ..Default::default()
            }
        )
        .is_err());
        assert!(t.join().unwrap().is_err());
    }
    #[test]
    fn oversized_and_nonlocal_invitations_rejected() {
        let mut invite = Receiver::new("127.0.0.1").unwrap().invitation;
        invite.host = "8.8.8.8".into();
        assert!(Invitation::parse(&invite.encode().unwrap()).is_err());
        let bytes = vec![0; MAX_BYTES + 1];
        assert!(frame_write(&mut Vec::new(), &bytes).is_err());
    }
}
