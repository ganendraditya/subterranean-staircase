use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE, USER_AGENT};
use serde::{Deserialize, Serialize};
use std::net::IpAddr;
use std::sync::Arc;
use std::time::{Duration, Instant};

use crate::cache::TranslationCache;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmConfig {
    pub base_url: String,
    pub model_name: String,
    pub api_key: Option<String>,
    pub timeout_seconds: Option<u64>,
}

impl LlmConfig {
    pub fn get_config_dir() -> std::path::PathBuf {
        let base = dirs::config_dir()
            .or_else(dirs::data_local_dir)
            .unwrap_or_else(|| std::path::PathBuf::from("."));
        base.join("subterranean-staircase")
    }

    pub fn get_config_path() -> std::path::PathBuf {
        Self::get_config_dir().join("llm_config.json")
    }

    pub fn load() -> Self {
        let path = Self::get_config_path();
        if path.exists() {
            if let Ok(contents) = std::fs::read_to_string(&path) {
                if let Ok(config) = serde_json::from_str::<Self>(&contents) {
                    return config;
                }
            }
        }
        Self::default()
    }

    pub fn save(&self) -> Result<(), String> {
        let dir = Self::get_config_dir();
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let path = Self::get_config_path();
        let json_str = serde_json::to_string_pretty(self).map_err(|e| e.to_string())?;

        let temp_path = path.with_extension("tmp");
        std::fs::write(&temp_path, json_str).map_err(|e| e.to_string())?;

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(&temp_path, std::fs::Permissions::from_mode(0o600));
        }

        std::fs::rename(&temp_path, &path).map_err(|e| e.to_string())?;

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
        }

        Ok(())
    }
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            base_url: "https://api.groq.com/openai/v1".to_string(),
            model_name: "llama-3.3-70b-versatile".to_string(),
            api_key: None,
            timeout_seconds: Some(10),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranslationRequest {
    pub source_text: String,
    pub source_lang: String,
    pub target_lang: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranslationResponse {
    pub source_text: String,
    pub translated_text: String,
    pub source_lang: String,
    pub target_lang: String,
    pub from_cache: bool,
    pub latency_ms: f32,
    #[serde(default)]
    pub is_fallback: bool,
}

#[derive(Debug, Clone, Default)]
pub struct OfflineTranslator;

impl OfflineTranslator {
    pub fn new() -> Self {
        Self
    }

    /// Translates text using local dictionary and linguistic heuristics for common Big 5 subtitle dialogue.
    pub fn translate(&self, source_text: &str, src_lang: &str, tgt_lang: &str) -> String {
        let cleaned = source_text.trim();
        if cleaned.is_empty() {
            return String::new();
        }

        let s_lower = cleaned.to_lowercase();
        let s_clean = s_lower.trim_matches(|c: char| c.is_ascii_punctuation() || c.is_whitespace());

        let src = src_lang.trim().to_lowercase();
        let tgt = tgt_lang.trim().to_lowercase();

        if let Some(trans) = Self::lookup_phrase(s_clean, &src, &tgt) {
            return trans.to_string();
        }

        // Return original text if not found in curated dictionary
        cleaned.to_string()
    }

    fn lookup_phrase(phrase: &str, src: &str, tgt: &str) -> Option<&'static str> {
        match (src, tgt) {
            ("en", "id") => match phrase {
                "hello" | "hi" => Some("Halo"),
                "thank you" | "thanks" => Some("Terima kasih"),
                "yes" | "yeah" | "yep" => Some("Ya"),
                "no" | "nope" => Some("Tidak"),
                "wait" | "wait a minute" | "hold on" => Some("Tunggu"),
                "what" | "what?" => Some("Apa?"),
                "who" | "who?" => Some("Siapa?"),
                "where" | "where?" => Some("Di mana?"),
                "why" | "why?" => Some("Kenapa?"),
                "how" | "how?" => Some("Bagaimana?"),
                "stop" => Some("Berhenti"),
                "let's go" | "lets go" => Some("Ayo pergi"),
                "help" | "help me" => Some("Tolong"),
                "please" => Some("Tolong"),
                "sorry" | "i'm sorry" => Some("Maaf"),
                "excuse me" => Some("Permisi"),
                "okay" | "ok" | "alright" => Some("Baiklah"),
                "goodbye" | "bye" => Some("Selamat tinggal"),
                "i see" | "i understand" => Some("Begitu rupanya"),
                "of course" => Some("Tentu saja"),
                "really" | "really?" => Some("Benarkah?"),
                "never" => Some("Tidak pernah"),
                "always" => Some("Selalu"),
                "stay hungry stay foolish" => Some("Tetap lapar, tetap bodoh"),
                _ => None,
            },
            ("id", "en") => match phrase {
                "halo" => Some("Hello"),
                "terima kasih" | "makasih" => Some("Thank you"),
                "ya" => Some("Yes"),
                "tidak" | "nggak" | "enggak" => Some("No"),
                "tunggu" | "tunggu sebentar" => Some("Wait"),
                "apa" | "apa?" => Some("What?"),
                "siapa" | "siapa?" => Some("Who?"),
                "di mana" | "dimana" => Some("Where?"),
                "kenapa" | "mengapa" => Some("Why?"),
                "tolong" | "bantu aku" => Some("Help"),
                "maaf" => Some("Sorry"),
                "permisi" => Some("Excuse me"),
                "baiklah" | "oke" => Some("Okay"),
                "ayo" | "ayo pergi" => Some("Let's go"),
                "selamat tinggal" | "sampai jumpa" => Some("Goodbye"),
                _ => None,
            },
            ("ja", "en") | ("auto", "en") => match phrase {
                "こんにちは" | "こんにちわ" => Some("Hello"),
                "ありがとう" | "ありがとうございます" => Some("Thank you"),
                "はい" => Some("Yes"),
                "いいえ" => Some("No"),
                "待って" | "ちょっと待って" => Some("Wait"),
                "何" | "なに" => Some("What?"),
                "誰" | "だれ" => Some("Who?"),
                "どこ" => Some("Where?"),
                "なぜ" | "どうして" => Some("Why?"),
                "助けて" => Some("Help!"),
                "行こう" => Some("Let's go"),
                "止まれ" | "やめて" => Some("Stop!"),
                "すみません" => Some("Excuse me"),
                "ごめんなさい" => Some("I'm sorry"),
                "大丈夫" | "だいじょうぶ" => Some("It's okay"),
                "さようなら" => Some("Goodbye"),
                "なるほど" => Some("I see"),
                _ => None,
            },
            ("ja", "id") | ("auto", "id") => match phrase {
                "こんにちは" | "こんにちわ" => Some("Halo"),
                "ありがとう" | "ありがとうございます" => Some("Terima kasih"),
                "はい" => Some("Ya"),
                "いいえ" => Some("Tidak"),
                "待って" | "ちょっと待って" => Some("Tunggu"),
                "何" | "なに" => Some("Apa?"),
                "誰" | "だれ" => Some("Siapa?"),
                "どこ" => Some("Di mana?"),
                "助けて" => Some("Tolong!"),
                "行こう" => Some("Ayo pergi"),
                "やめて" | "止まれ" => Some("Hentikan!"),
                "すみません" => Some("Permisi"),
                "ごめんなさい" => Some("Maafkan aku"),
                "大丈夫" | "だいじょうぶ" => Some("Tidak apa-apa"),
                "さようなら" => Some("Selamat tinggal"),
                _ => None,
            },
            ("zh", "en") => match phrase {
                "你好" => Some("Hello"),
                "谢谢" => Some("Thank you"),
                "是的" | "对" => Some("Yes"),
                "不是" | "不" => Some("No"),
                "等等" => Some("Wait"),
                "什么" => Some("What?"),
                "救命" => Some("Help!"),
                "走吧" => Some("Let's go"),
                "再见" => Some("Goodbye"),
                _ => None,
            },
            ("zh", "id") => match phrase {
                "你好" => Some("Halo"),
                "谢谢" => Some("Terima kasih"),
                "是的" | "对" => Some("Ya"),
                "不是" | "不" => Some("Tidak"),
                "等等" => Some("Tunggu"),
                "什么" => Some("Apa?"),
                "救命" => Some("Tolong!"),
                "走吧" => Some("Ayo pergi"),
                "再见" => Some("Sampai jumpa"),
                _ => None,
            },
            ("ko", "en") => match phrase {
                "안녕하세요" => Some("Hello"),
                "감사합니다" | "고마워" => Some("Thank you"),
                "네" | "예" => Some("Yes"),
                "아니요" | "아니" => Some("No"),
                "잠깐만" | "기다려" => Some("Wait"),
                "뭐야" | "뭐" => Some("What?"),
                "도와줘" | "살려줘" => Some("Help!"),
                "가자" => Some("Let's go"),
                "안녕" => Some("Goodbye"),
                _ => None,
            },
            ("ko", "id") => match phrase {
                "안녕하세요" => Some("Halo"),
                "감사합니다" | "고마워" => Some("Terima kasih"),
                "네" | "예" => Some("Ya"),
                "아니요" | "아니" => Some("Tidak"),
                "잠깐만" | "기다려" => Some("Tunggu sebentar"),
                "뭐야" | "뭐" => Some("Apa?"),
                "도와줘" | "살려줘" => Some("Tolong!"),
                "가자" => Some("Ayo"),
                "안녕" => Some("Sampai jumpa"),
                _ => None,
            },
            _ => None,
        }
    }
}

#[derive(Serialize)]
struct ChatMessage<'a> {
    role: &'a str,
    content: &'a str,
}

#[derive(Serialize)]
struct ChatCompletionPayload<'a> {
    model: &'a str,
    messages: Vec<ChatMessage<'a>>,
    temperature: f32,
    max_tokens: u32,
}

#[derive(Deserialize)]
struct ChatCompletionResponse {
    choices: Option<Vec<ChatChoice>>,
}

#[derive(Deserialize)]
struct ChatChoice {
    message: Option<ChoiceMessage>,
}

#[derive(Deserialize)]
struct ChoiceMessage {
    content: Option<String>,
}

pub fn truncate_utf8(s: &str, max_bytes: usize) -> &str {
    if s.len() <= max_bytes {
        return s;
    }
    let mut end = max_bytes;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    &s[..end]
}

pub fn clamp_timeout(secs: Option<u64>, default_secs: u64) -> Duration {
    let bounded = secs.unwrap_or(default_secs).clamp(1, 120);
    Duration::from_secs(bounded)
}

pub fn normalize_chat_endpoint(base_url: &str) -> Result<String, String> {
    let raw = base_url.trim();
    if raw.is_empty() {
        return Ok("https://api.groq.com/openai/v1/chat/completions".to_string());
    }

    let parsed = reqwest::Url::parse(raw)
        .map_err(|e| format!("Invalid base URL '{}': {}", raw, e))?;

    // Scheme whitelist: only http and https are allowed
    let scheme = parsed.scheme();
    if scheme != "http" && scheme != "https" {
        return Err(format!(
            "Unsupported scheme '{}'. Only 'http' and 'https' are allowed.",
            scheme
        ));
    }

    // Disallow query parameters, URL fragments, or embedded user credentials
    if parsed.query().is_some()
        || parsed.fragment().is_some()
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return Err(
            "Base URL must not contain query parameters, fragments, or embedded credentials."
                .to_string(),
        );
    }

    // SSRF mitigation: block link-local addresses, IPv4-mapped IPv6, and cloud metadata service
    if let Some(host_str) = parsed.host_str() {
        let clean_host = host_str.trim_start_matches('[').trim_end_matches(']');
        if clean_host == "169.254.169.254" {
            return Err("Access to cloud metadata service (169.254.169.254) is forbidden.".to_string());
        }
        if let Ok(ip) = clean_host.parse::<IpAddr>() {
            match ip {
                IpAddr::V4(ipv4) => {
                    if ipv4.is_link_local() {
                        return Err(format!(
                            "Access to IPv4 link-local address '{}' is forbidden.",
                            ipv4
                        ));
                    }
                }
                IpAddr::V6(ipv6) => {
                    if let Some(ipv4) = ipv6.to_ipv4_mapped() {
                        if ipv4.is_link_local() || ipv4.to_string() == "169.254.169.254" {
                            return Err(format!(
                                "Access to mapped IPv4 link-local address '{}' is forbidden.",
                                ipv4
                            ));
                        }
                    }
                    let segments = ipv6.segments();
                    if (segments[0] & 0xffc0) == 0xfe80 {
                        return Err(format!(
                            "Access to IPv6 link-local address '{}' is forbidden.",
                            ipv6
                        ));
                    }
                }
            }
        }
    }

    let url_str = raw.trim_end_matches('/');
    if url_str.ends_with("/chat/completions") {
        Ok(url_str.to_string())
    } else if url_str.ends_with("/v1") {
        Ok(format!("{}/chat/completions", url_str))
    } else {
        Ok(format!("{}/v1/chat/completions", url_str))
    }
}

pub fn get_language_display_name(code: &str) -> String {
    match code.trim().to_lowercase().as_str() {
        "en" => "English".to_string(),
        "id" => "Indonesian".to_string(),
        "ja" => "Japanese".to_string(),
        "zh" => "Chinese".to_string(),
        "ko" => "Korean".to_string(),
        "es" => "Spanish".to_string(),
        "fr" => "French".to_string(),
        "de" => "German".to_string(),
        "auto" => "Auto-Detect".to_string(),
        other => other.to_uppercase(),
    }
}

pub fn sanitize_llm_translation(raw: &str) -> String {
    let mut out = raw.trim().to_string();

    // Strip outer quotes
    if (out.starts_with('"') && out.ends_with('"'))
        || (out.starts_with('\'') && out.ends_with('\''))
    {
        if out.len() >= 2 {
            out = out[1..out.len() - 1].trim().to_string();
        }
    }

    // Strip markdown code fences (``` ... ```)
    if out.starts_with("```") && out.ends_with("```") {
        let lines: Vec<&str> = out.lines().collect();
        if lines.len() >= 3 {
            out = lines[1..lines.len() - 1].join("\n").trim().to_string();
        } else {
            out = out.trim_matches('`').trim().to_string();
        }
    }

    out
}

pub struct LlmTranslator {
    client: reqwest::Client,
    cache: Arc<TranslationCache>,
    pub offline_translator: OfflineTranslator,
}

impl LlmTranslator {
    pub fn new(cache: Arc<TranslationCache>) -> Self {
        let client = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        Self {
            client,
            cache,
            offline_translator: OfflineTranslator::new(),
        }
    }

    pub fn translate_blocking(
        &self,
        config: &LlmConfig,
        req: &TranslationRequest,
    ) -> Result<TranslationResponse, String> {
        let cleaned_source = req.source_text.trim();
        let src_code = req.source_lang.trim().to_lowercase();
        let tgt_code = req.target_lang.trim().to_lowercase();

        // 1. Identity Check
        if src_code == tgt_code && src_code != "auto" {
            return Ok(TranslationResponse {
                source_text: req.source_text.clone(),
                translated_text: cleaned_source.to_string(),
                source_lang: src_code,
                target_lang: tgt_code,
                from_cache: false,
                latency_ms: 0.0,
                is_fallback: false,
            });
        }

        // 2. High-concurrency Cache Lookup (< 1 ms instant response)
        if let Some(cached_text) = self.cache.get(cleaned_source, &src_code, &tgt_code) {
            return Ok(TranslationResponse {
                source_text: req.source_text.clone(),
                translated_text: cached_text,
                source_lang: src_code,
                target_lang: tgt_code,
                from_cache: true,
                latency_ms: 0.0,
                is_fallback: false,
            });
        }

        tauri::async_runtime::block_on(self.translate(config, req))
    }

    pub async fn translate(
        &self,
        config: &LlmConfig,
        req: &TranslationRequest,
    ) -> Result<TranslationResponse, String> {
        let start = Instant::now();
        let cleaned_source = req.source_text.trim();
        if cleaned_source.is_empty() {
            return Ok(TranslationResponse {
                source_text: req.source_text.clone(),
                translated_text: String::new(),
                source_lang: req.source_lang.clone(),
                target_lang: req.target_lang.clone(),
                from_cache: false,
                latency_ms: 0.0,
                is_fallback: false,
            });
        }

        let src_code = req.source_lang.trim().to_lowercase();
        let tgt_code = req.target_lang.trim().to_lowercase();

        // 1. Identity Check
        if src_code == tgt_code && src_code != "auto" {
            let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
            return Ok(TranslationResponse {
                source_text: req.source_text.clone(),
                translated_text: cleaned_source.to_string(),
                source_lang: src_code,
                target_lang: tgt_code,
                from_cache: false,
                latency_ms,
                is_fallback: false,
            });
        }

        // 2. High-concurrency Cache Lookup (< 1 ms instant response)
        if let Some(cached_text) = self.cache.get(cleaned_source, &src_code, &tgt_code) {
            let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
            return Ok(TranslationResponse {
                source_text: req.source_text.clone(),
                translated_text: cached_text,
                source_lang: src_code,
                target_lang: tgt_code,
                from_cache: true,
                latency_ms,
                is_fallback: false,
            });
        }

        // 3. Remote OpenAI-compatible API Dispatch
        let endpoint_res = normalize_chat_endpoint(&config.base_url);
        let endpoint = match endpoint_res {
            Ok(ep) => ep,
            Err(_) => {
                // Fallback directly to offline translation on invalid endpoint without poisoning persistent cache
                let fallback = self.offline_translator.translate(cleaned_source, &src_code, &tgt_code);
                let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
                return Ok(TranslationResponse {
                    source_text: req.source_text.clone(),
                    translated_text: fallback,
                    source_lang: src_code,
                    target_lang: tgt_code,
                    from_cache: false,
                    latency_ms,
                    is_fallback: true,
                });
            }
        };

        let src_name = get_language_display_name(&src_code);
        let tgt_name = get_language_display_name(&tgt_code);

        let system_instruction = if src_code == "auto" {
            format!(
                "You are a professional real-time subtitle translator. \
                 Translate the given dialogue into {}. \
                 Output ONLY the direct translated text. \
                 Do NOT include explanations, notes, quotes, or markdown formatting.",
                tgt_name
            )
        } else {
            format!(
                "You are a professional real-time subtitle translator. \
                 Translate the given dialogue from {} to {}. \
                 Output ONLY the direct translated text. \
                 Do NOT include explanations, notes, quotes, or markdown formatting.",
                src_name, tgt_name
            )
        };

        let model = if config.model_name.trim().is_empty() {
            "llama-3.3-70b-versatile"
        } else {
            config.model_name.trim()
        };

        let payload = ChatCompletionPayload {
            model,
            messages: vec![
                ChatMessage {
                    role: "system",
                    content: &system_instruction,
                },
                ChatMessage {
                    role: "user",
                    content: cleaned_source,
                },
            ],
            temperature: 0.1,
            max_tokens: 180,
        };

        let mut headers = HeaderMap::new();
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        headers.insert(
            USER_AGENT,
            HeaderValue::from_static("Subterranean-Staircase/2.0"),
        );

        if let Some(key) = &config.api_key {
            let trimmed = key.trim();
            if !trimmed.is_empty() {
                if let Ok(val) = HeaderValue::from_str(&format!("Bearer {}", trimmed)) {
                    headers.insert(AUTHORIZATION, val);
                }
            }
        }

        let timeout = clamp_timeout(config.timeout_seconds, 10);

        let remote_call = async {
            let resp = self
                .client
                .post(&endpoint)
                .headers(headers)
                .json(&payload)
                .timeout(timeout)
                .send()
                .await
                .map_err(|e| format!("HTTP request to '{}' failed: {}", endpoint, e))?;

            let status = resp.status();
            if !status.is_success() {
                let error_body = resp
                    .text()
                    .await
                    .unwrap_or_else(|_| "Unknown error response".to_string());
                let trimmed_body = error_body.trim();
                let truncated = truncate_utf8(trimmed_body, 250);
                let sanitized_body = if trimmed_body.len() > truncated.len() {
                    format!("{}...", truncated)
                } else {
                    truncated.to_string()
                };
                return Err(format!(
                    "API returned error status {} ({}): {}",
                    status.as_u16(),
                    status.canonical_reason().unwrap_or("Error"),
                    sanitized_body
                ));
            }

            let completion: ChatCompletionResponse = resp
                .json()
                .await
                .map_err(|e| format!("Failed to parse response JSON: {}", e))?;

            let raw_content = completion
                .choices
                .and_then(|c| c.into_iter().next())
                .and_then(|c| c.message)
                .and_then(|m| m.content)
                .ok_or_else(|| "API response contained no message content".to_string())?;

            Ok(sanitize_llm_translation(&raw_content))
        };

        match remote_call.await {
            Ok(translated_text) => {
                let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
                if !translated_text.is_empty() {
                    self.cache
                        .set(cleaned_source, &src_code, &tgt_code, &translated_text);
                }
                Ok(TranslationResponse {
                    source_text: req.source_text.clone(),
                    translated_text,
                    source_lang: src_code,
                    target_lang: tgt_code,
                    from_cache: false,
                    latency_ms,
                    is_fallback: false,
                })
            }
            Err(err) => {
                // Automatic graceful fallback to offline translation engine without poisoning persistent cache
                eprintln!("[LLM-FALLBACK] Remote translation unavailable ({err}), falling back to offline engine");
                let fallback = self.offline_translator.translate(cleaned_source, &src_code, &tgt_code);
                let latency_ms = start.elapsed().as_secs_f32() * 1000.0;
                Ok(TranslationResponse {
                    source_text: req.source_text.clone(),
                    translated_text: fallback,
                    source_lang: src_code,
                    target_lang: tgt_code,
                    from_cache: false,
                    latency_ms,
                    is_fallback: true,
                })
            }
        }
    }

    pub async fn test_connection(&self, config: &LlmConfig) -> Result<String, String> {
        // Bypass cache check for connectivity probe
        let endpoint = normalize_chat_endpoint(&config.base_url)?;
        let payload = ChatCompletionPayload {
            model: if config.model_name.trim().is_empty() {
                "llama-3.3-70b-versatile"
            } else {
                config.model_name.trim()
            },
            messages: vec![ChatMessage {
                role: "user",
                content: "Reply strictly with the word: OK",
            }],
            temperature: 0.0,
            max_tokens: 10,
        };

        let mut headers = HeaderMap::new();
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        headers.insert(
            USER_AGENT,
            HeaderValue::from_static("Subterranean-Staircase/2.0"),
        );

        if let Some(key) = &config.api_key {
            let trimmed = key.trim();
            if !trimmed.is_empty() {
                if let Ok(val) = HeaderValue::from_str(&format!("Bearer {}", trimmed)) {
                    headers.insert(AUTHORIZATION, val);
                }
            }
        }

        let timeout = clamp_timeout(config.timeout_seconds, 8);
        let t0 = Instant::now();

        let resp = self
            .client
            .post(&endpoint)
            .headers(headers)
            .json(&payload)
            .timeout(timeout)
            .send()
            .await
            .map_err(|e| format!("Connection to '{}' failed: {}", endpoint, e))?;

        let status = resp.status();
        let lat = t0.elapsed().as_secs_f32() * 1000.0;
        if status.is_success() {
            Ok(format!(
                "Connection successful! HTTP 200 OK ({:.1} ms)",
                lat
            ))
        } else {
            let body = resp.text().await.unwrap_or_default();
            let trimmed_body = body.trim();
            let truncated = truncate_utf8(trimmed_body, 250);
            let sanitized_body = if trimmed_body.len() > truncated.len() {
                format!("{}...", truncated)
            } else {
                truncated.to_string()
            };
            Err(format!(
                "API returned error {}: {}",
                status.as_u16(),
                sanitized_body
            ))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_chat_endpoint() {
        assert_eq!(
            normalize_chat_endpoint("").unwrap(),
            "https://api.groq.com/openai/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("https://api.openai.com").unwrap(),
            "https://api.openai.com/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("https://api.openai.com/v1").unwrap(),
            "https://api.openai.com/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("http://localhost:11434/v1/").unwrap(),
            "http://localhost:11434/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("https://custom.provider.com/chat/completions").unwrap(),
            "https://custom.provider.com/chat/completions"
        );
        // SSRF protection: reject cloud metadata & unsupported schemes
        assert!(normalize_chat_endpoint("http://169.254.169.254/v1").is_err());
        assert!(normalize_chat_endpoint("http://169.254.1.2/v1").is_err());
        assert!(normalize_chat_endpoint("http://[fe80::1]/v1").is_err());
        assert!(normalize_chat_endpoint("ftp://example.com/v1").is_err());
        assert!(normalize_chat_endpoint("file:///etc/passwd").is_err());
        // Disallow query params or fragments on base_url
        assert!(normalize_chat_endpoint("https://api.openai.com/v1?query=1").is_err());
        assert!(normalize_chat_endpoint("https://api.openai.com/v1#hash").is_err());
    }

    #[test]
    fn test_truncate_utf8_multibyte_safety() {
        let ascii = "abcdefghij";
        assert_eq!(truncate_utf8(ascii, 5), "abcde");
        assert_eq!(truncate_utf8(ascii, 20), "abcdefghij");

        // Japanese 3-byte character 'あ' (0xE3, 0x81, 0x82) repeated
        let japanese = "あああ"; // 9 bytes total (3 bytes each)
        // Requesting 4 bytes cuts in the middle of second character, should truncate safely to 3 bytes
        assert_eq!(truncate_utf8(japanese, 4), "あ");
        assert_eq!(truncate_utf8(japanese, 6), "ああ");
    }

    #[test]
    fn test_clamp_timeout() {
        assert_eq!(clamp_timeout(None, 10), Duration::from_secs(10));
        assert_eq!(clamp_timeout(Some(0), 10), Duration::from_secs(1));
        assert_eq!(clamp_timeout(Some(500), 10), Duration::from_secs(120));
        assert_eq!(clamp_timeout(Some(30), 10), Duration::from_secs(30));
    }

    #[test]
    fn test_get_language_display_name() {
        assert_eq!(get_language_display_name("en"), "English");
        assert_eq!(get_language_display_name("id"), "Indonesian");
        assert_eq!(get_language_display_name("ja"), "Japanese");
        assert_eq!(get_language_display_name("auto"), "Auto-Detect");
        assert_eq!(get_language_display_name("fr"), "French");
        assert_eq!(get_language_display_name("custom"), "CUSTOM");
    }

    #[test]
    fn test_sanitize_llm_translation() {
        assert_eq!(sanitize_llm_translation("\"Hello world\""), "Hello world");
        assert_eq!(sanitize_llm_translation("'Translated'"), "Translated");
        assert_eq!(
            sanitize_llm_translation("```text\nClean line\n```"),
            "Clean line"
        );
        assert_eq!(sanitize_llm_translation("```No fence```"), "No fence");
        assert_eq!(sanitize_llm_translation("  Direct Text  "), "Direct Text");
    }

    #[tokio::test]
    async fn test_translator_cache_hit_bypasses_network() {
        let cache = Arc::new(TranslationCache::open_in_memory().expect("open memory cache"));
        cache.set("Stay Hungry", "en", "id", "Tetap Lapar");

        let translator = LlmTranslator::new(cache.clone());
        let config = LlmConfig::default();
        let req = TranslationRequest {
            source_text: "Stay Hungry".to_string(),
            source_lang: "en".to_string(),
            target_lang: "id".to_string(),
        };

        // Cache hit must return immediately with from_cache = true
        let res = translator
            .translate(&config, &req)
            .await
            .expect("translation response");
        assert_eq!(res.translated_text, "Tetap Lapar");
        assert!(res.from_cache);
        assert!(res.latency_ms >= 0.0 && res.latency_ms < 50.0);
    }

    #[tokio::test]
    async fn test_identity_translation_returns_immediately() {
        let cache = Arc::new(TranslationCache::open_in_memory().expect("open memory cache"));
        let translator = LlmTranslator::new(cache);
        let config = LlmConfig::default();
        let req = TranslationRequest {
            source_text: "Identical Text".to_string(),
            source_lang: "en".to_string(),
            target_lang: "en".to_string(),
        };

        let res = translator
            .translate(&config, &req)
            .await
            .expect("translation response");
        assert_eq!(res.translated_text, "Identical Text");
        assert!(!res.from_cache);
        assert!(res.latency_ms >= 0.0 && res.latency_ms < 50.0);
    }

    #[test]
    fn test_offline_translator_dictionary() {
        let offline = OfflineTranslator::new();
        assert_eq!(offline.translate("Hello", "en", "id"), "Halo");
        assert_eq!(offline.translate("Thank you!", "en", "id"), "Terima kasih");
        assert_eq!(offline.translate("ありがとう", "ja", "en"), "Thank you");
        assert_eq!(offline.translate("こんにちは", "ja", "id"), "Halo");
        assert_eq!(offline.translate("你好", "zh", "en"), "Hello");
        assert_eq!(offline.translate("안녕하세요", "ko", "id"), "Halo");
        // Unknown phrase fallback keeps original cleanly
        assert_eq!(offline.translate("Random Unseen Line", "en", "id"), "Random Unseen Line");
    }

    #[tokio::test]
    async fn test_offline_fallback_on_network_failure() {
        let cache = Arc::new(TranslationCache::open_in_memory().expect("open memory cache"));
        let translator = LlmTranslator::new(cache);
        // Invalid/unreachable local port to simulate network failure
        let config = LlmConfig {
            base_url: "http://127.0.0.1:54321/v1".to_string(),
            model_name: "test-model".to_string(),
            api_key: None,
            timeout_seconds: Some(1),
        };
        let req = TranslationRequest {
            source_text: "Thank you".to_string(),
            source_lang: "en".to_string(),
            target_lang: "id".to_string(),
        };

        let res = translator
            .translate(&config, &req)
            .await
            .expect("fallback response");
        assert_eq!(res.translated_text, "Terima kasih");
        assert!(res.is_fallback);
        assert!(!res.from_cache);
    }
}
