use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE, USER_AGENT};
use serde::{Deserialize, Serialize};
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

pub fn normalize_chat_endpoint(base_url: &str) -> String {
    let url = base_url.trim().trim_end_matches('/');
    if url.is_empty() {
        return "https://api.groq.com/openai/v1/chat/completions".to_string();
    }
    if url.ends_with("/chat/completions") {
        return url.to_string();
    }
    if url.ends_with("/v1") {
        format!("{}/chat/completions", url)
    } else {
        format!("{}/v1/chat/completions", url)
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
}

impl LlmTranslator {
    pub fn new(cache: Arc<TranslationCache>) -> Self {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(15))
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        Self { client, cache }
    }

    pub async fn translate(
        &self,
        config: &LlmConfig,
        req: &TranslationRequest,
    ) -> Result<TranslationResponse, String> {
        let cleaned_source = req.source_text.trim();
        if cleaned_source.is_empty() {
            return Ok(TranslationResponse {
                source_text: req.source_text.clone(),
                translated_text: String::new(),
                source_lang: req.source_lang.clone(),
                target_lang: req.target_lang.clone(),
                from_cache: false,
                latency_ms: 0.0,
            });
        }

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
            });
        }

        // 3. Remote OpenAI-compatible API Dispatch
        let endpoint = normalize_chat_endpoint(&config.base_url);
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

        let timeout = Duration::from_secs(config.timeout_seconds.unwrap_or(10).max(1));

        let t0 = Instant::now();
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
            return Err(format!(
                "API returned error status {} ({}): {}",
                status.as_u16(),
                status.canonical_reason().unwrap_or("Error"),
                error_body
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

        let translated_text = sanitize_llm_translation(&raw_content);
        let latency_ms = t0.elapsed().as_secs_f32() * 1000.0;

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
        })
    }

    pub async fn test_connection(&self, config: &LlmConfig) -> Result<String, String> {
        // Bypass cache check for connectivity probe
        let endpoint = normalize_chat_endpoint(&config.base_url);
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

        let timeout = Duration::from_secs(config.timeout_seconds.unwrap_or(8).max(1));
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
            Err(format!(
                "API returned error {}: {}",
                status.as_u16(),
                body
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
            normalize_chat_endpoint(""),
            "https://api.groq.com/openai/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("https://api.openai.com"),
            "https://api.openai.com/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("https://api.openai.com/v1"),
            "https://api.openai.com/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("http://localhost:11434/v1/"),
            "http://localhost:11434/v1/chat/completions"
        );
        assert_eq!(
            normalize_chat_endpoint("https://custom.provider.com/chat/completions"),
            "https://custom.provider.com/chat/completions"
        );
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
        assert_eq!(res.latency_ms, 0.0);
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
        assert_eq!(res.latency_ms, 0.0);
    }
}
