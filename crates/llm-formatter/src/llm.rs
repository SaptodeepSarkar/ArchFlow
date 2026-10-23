//! LLM formatter backend: the PRD's "take the raw STT data and feed that to
//! the LLM, then type the LLM output".
//!
//! Talks HTTP/1.1 to a local llama-server (`/v1/chat/completions`) over a
//! std TcpStream, so there is no HTTP dependency. The rule engine stays as
//! the fallback: if the endpoint is down, slow, or answers with something
//! that fails [`looks_like_formatting`], the caller keeps the deterministic
//! output rather than typing a model's musings.

use std::io::{ErrorKind, Read, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};

/// Transcript longer than this times the input is treated as rambling, not
/// formatting (a dictation never triples in length).
const MAX_GROWTH: usize = 3;

/// Silence longer than this means the server is wedged, not thinking.
const IDLE_TIMEOUT: Duration = Duration::from_secs(5);
/// Total budget for a reply: a cold model on a long dictation can take a
/// while, but the utterance still never waits forever.
const REPLY_DEADLINE: Duration = Duration::from_secs(60);

/// Default endpoint: a llama-server on this machine (any OpenAI-compatible
/// chat endpoint works via `VAANI_LLM_ENDPOINT`).
pub fn default_endpoint() -> String {
    std::env::var("VAANI_LLM_ENDPOINT").unwrap_or_else(|_| "http://127.0.0.1:8081".to_string())
}

/// The instruction the PRD's formatter has to follow. Kept in one place so
/// the prompt is reviewable next to the rules the rule engine implements.
fn prompt(vocab: &[(String, String)]) -> String {
    let mut p = String::from(
        "You format dictated speech into clean written text.\n\
         Rules:\n\
         1. Remove filler words (umm, hmm, uh, er, ah, like as filler).\n\
         2. If the speaker corrects themselves, keep only the correction.\n\
         3. Fix capitalization and punctuation. Keep the speaker's wording.\n\
         4. Never add, explain, translate, or comment. No quotes around the result.\n\
         5. Reply with ONLY the formatted text.\n\
         Example: input \"umm so i think hmm we should ship it\" -> \
         output \"So I think we should ship it.\"\n",
    );
    if !vocab.is_empty() {
        p.push_str("6. Replace these spoken words with exactly this text:\n");
        for (spoken, typed) in vocab {
            p.push_str(&format!("   \"{spoken}\" -> \"{typed}\"\n"));
        }
    }
    p
}

/// Format `raw` with the LLM at `endpoint`. `None` means "keep the rule
/// engine's output" and the reason is printed to stderr.
pub fn format_llm(raw: &str, endpoint: &str, vocab: &[(String, String)]) -> Option<String> {
    let body = build_request(raw, &prompt(vocab));
    let response = match post(endpoint, &body) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("llm-formatter: {endpoint} unavailable ({e}); using rule engine");
            return None;
        }
    };
    let Some(content) = extract_content(&response) else {
        eprintln!("llm-formatter: no message content in the response; using rule engine");
        return None;
    };
    let text = strip_ack(content.trim().trim_matches('"').trim())
        .trim_matches('"')
        .trim();
    if !looks_like_formatting(raw, text) {
        eprintln!("llm-formatter: response rejected as unformatted; using rule engine");
        return None;
    }
    Some(text.to_string())
}

/// Acknowledgment openers the prompt forbids but models still emit.
const ACKS: &[&str] = &[
    "sure",
    "certainly",
    "of course",
    "okay",
    "here is",
    "here's",
    "the formatted text",
];

/// Drop the model's acknowledgment opener ("Sure, here is the formatted
/// text:") so the formatting underneath is typed instead of the whole reply
/// being rejected. Only a leading line, or the text before a colon, that opens
/// with a known ack is removed; anything else is returned untouched.
fn strip_ack(out: &str) -> &str {
    let mut text = out.trim();
    while ACKS.iter().any(|a| text.to_ascii_lowercase().starts_with(a)) {
        let rest = match text.split_once('\n') {
            Some((_, tail)) => tail,
            None => match text.split_once(':') {
                Some((_, tail)) => tail,
                None => break,
            },
        };
        if rest.trim().is_empty() {
            break;
        }
        text = rest.trim();
    }
    text
}

/// Sanity gate on a model response: non-empty, not a preamble, not wildly
/// longer than what was said.
fn looks_like_formatting(raw: &str, out: &str) -> bool {
    if out.is_empty() {
        return false;
    }
    let lower = out.to_ascii_lowercase();
    for bad in ["here is", "sure", "as an ai", "the formatted", "i cannot"] {
        if lower.starts_with(bad) {
            return false;
        }
    }
    out.len() <= raw.len().max(24) * MAX_GROWTH
}

fn build_request(raw: &str, instruction: &str) -> String {
    let payload = format!(
        "{{\"messages\":[{{\"role\":\"system\",\"content\":{}}},{{\"role\":\"user\",\"content\":{}}}],\
         \"temperature\":0.1,\"max_tokens\":512,\"stream\":false}}",
        json_string(instruction),
        json_string(raw),
    );
    payload
}

/// Minimal JSON string encoding for the request body.
fn json_string(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// POST the payload to `<endpoint>/v1/chat/completions`.
fn post(endpoint: &str, body: &str) -> Result<String, String> {
    let rest = endpoint
        .strip_prefix("http://")
        .ok_or_else(|| "only http:// endpoints are supported".to_string())?;
    let (host_port, _) = rest.split_once('/').unwrap_or((rest, ""));
    let (host, port) = match host_port.split_once(':') {
        Some((h, p)) => (h.to_string(), p.parse::<u16>().map_err(|e| e.to_string())?),
        None => (host_port.to_string(), 80u16),
    };
    let addr = if host == "localhost" { "127.0.0.1" } else { &host };
    let mut stream = TcpStream::connect((addr, port)).map_err(|e| e.to_string())?;
    stream
        .set_read_timeout(Some(IDLE_TIMEOUT))
        .map_err(|e| e.to_string())?;
    let request = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: {host}:{port}\r\n\
         Content-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|e| e.to_string())?;
    // Idle timeout catches a wedged server; the deadline gives a cold or slow
    // model room to answer a long dictation.
    let deadline = Instant::now() + REPLY_DEADLINE;
    let mut response = Vec::new();
    let mut buf = [0u8; 8192];
    loop {
        match stream.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => response.extend_from_slice(&buf[..n]),
            Err(e)
                if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut)
                    && Instant::now() < deadline => {}
            Err(e) => return Err(e.to_string()),
        }
    }
    String::from_utf8(response).map_err(|e| e.to_string())
}

/// Pull the assistant text out of an OpenAI-shaped response. Returns the
/// first `contents` value; llama-server always answers in that shape.
fn extract_content(response: &str) -> Option<String> {
    let body = response.split("\r\n\r\n").nth(1).unwrap_or(response);
    let key = "\"content\":";
    let start = body.find(key)? + key.len();
    unescape_json(body[start..].trim_start())
}

/// Parse a JSON string literal starting at `s[0]` (which must be `"`).
fn unescape_json(s: &str) -> Option<String> {
    let mut chars = s.chars();
    if chars.next()? != '"' {
        return None;
    }
    let mut out = String::new();
    while let Some(c) = chars.next() {
        match c {
            '"' => return Some(out),
            '\\' => match chars.next()? {
                'n' => out.push('\n'),
                'r' => out.push('\r'),
                't' => out.push('\t'),
                'u' => {
                    let hex: String = chars.by_ref().take(4).collect();
                    let code = u32::from_str_radix(&hex, 16).ok()?;
                    out.push(char::from_u32(code)?);
                }
                other => out.push(other),
            },
            c => out.push(c),
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn content_is_extracted_from_a_chat_response() {
        let resp = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n\
            {\"choices\":[{\"message\":{\"role\":\"assistant\",\"content\":\"Hello there.\"}}]}";
        assert_eq!(extract_content(resp).as_deref(), Some("Hello there."));
    }

    #[test]
    fn escaped_content_round_trips() {
        let resp = "{\"content\":\"line \\\"quoted\\\" and newline\\nend\"}";
        assert_eq!(
            extract_content(resp).as_deref(),
            Some("line \"quoted\" and newline\nend")
        );
    }

    #[test]
    fn request_body_is_valid_json_with_both_messages() {
        let body = build_request("umm hello", "format it");
        assert!(body.contains("\"role\":\"system\""), "system prompt missing");
        assert!(body.contains("\"role\":\"user\""), "user message missing");
        assert!(body.contains("umm hello"), "transcript missing");
        // Quotes and newlines must not break out of the JSON string.
        let tricky = build_request("say \"hi\"\nthen stop", "x");
        assert!(tricky.contains("say \\\"hi\\\"\\nthen stop"), "escaping broken: {tricky}");
    }

    #[test]
    fn rambling_and_preambles_are_rejected() {
        assert!(looks_like_formatting("hello", "Hello."));
        assert!(!looks_like_formatting("hello", ""));
        assert!(!looks_like_formatting("hello", "Sure, here is the formatted text: Hello."));
        assert!(!looks_like_formatting("hi", &"word ".repeat(50)));
    }

    #[test]
    fn acknowledgement_openers_are_stripped_not_rejected() {
        let raw = "umm so i think we should ship it";
        assert_eq!(
            strip_ack("Sure, here is the formatted text:\nSo I think we should ship it."),
            "So I think we should ship it."
        );
        assert_eq!(strip_ack("Sure: So I think we should ship it."), "So I think we should ship it.");
        assert!(looks_like_formatting(
            raw,
            strip_ack("Sure, here is the formatted text: \"So I think we should ship it.\"")
                .trim_matches('"')
        ));
        // Text that merely starts with an ack and has no preamble is untouched.
        assert_eq!(strip_ack("Sure."), "Sure.");
        assert_eq!(strip_ack("So I think we should ship it."), "So I think we should ship it.");
    }

    #[test]
    fn vocab_reaches_the_prompt() {
        let p = prompt(&[("github".to_string(), "https://github.com/x".to_string())]);
        assert!(p.contains("github"));
        assert!(p.contains("https://github.com/x"));
    }
}
