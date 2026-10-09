use rusqlite::{params, Connection, Result as SqlResult};
use std::fs::create_dir_all;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

pub struct TranslationCache {
    conn: Mutex<Connection>,
    max_entries: usize,
}

impl TranslationCache {
    pub fn get_default_db_path() -> PathBuf {
        let base = dirs::data_local_dir()
            .or_else(dirs::config_dir)
            .unwrap_or_else(|| PathBuf::from("."));
        base.join("subterranean-staircase").join("translations.db")
    }

    /// Open or create database in standard OS directory with WAL mode enabled.
    pub fn open_default() -> Result<Self, String> {
        let db_path = Self::get_default_db_path();
        if let Some(parent) = db_path.parent() {
            create_dir_all(parent).map_err(|e| {
                format!(
                    "Failed to create cache directory '{}': {}",
                    parent.display(),
                    e
                )
            })?;
        }
        Self::open_path(db_path).map_err(|e| e.to_string())
    }

    /// Open database at a specific path.
    pub fn open_path<P: AsRef<Path>>(path: P) -> SqlResult<Self> {
        let conn = Connection::open(path)?;
        Self::init_with_connection(conn)
    }

    /// Open in-memory database (ideal for tests and ephemeral sessions).
    pub fn open_in_memory() -> SqlResult<Self> {
        let conn = Connection::open_in_memory()?;
        Self::init_with_connection(conn)
    }

    fn init_with_connection(conn: Connection) -> SqlResult<Self> {
        // High-concurrency WAL configuration
        conn.execute_batch(
            "PRAGMA journal_mode = WAL;
             PRAGMA synchronous = NORMAL;
             PRAGMA busy_timeout = 5000;
             CREATE TABLE IF NOT EXISTS translations (
                 source_text TEXT NOT NULL,
                 source_lang TEXT NOT NULL,
                 target_lang TEXT NOT NULL,
                 translated_text TEXT NOT NULL,
                 access_count INTEGER NOT NULL DEFAULT 1,
                 last_accessed REAL NOT NULL,
                 created_at REAL NOT NULL,
                 PRIMARY KEY (source_text, source_lang, target_lang)
             );
             CREATE INDEX IF NOT EXISTS idx_translations_lru ON translations (last_accessed);",
        )?;

        Ok(Self {
            conn: Mutex::new(conn),
            max_entries: 10000,
        })
    }

    fn now_epoch_secs() -> f64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0)
    }

    /// Retrieve cached translation and update LRU last_accessed timestamp.
    pub fn get(&self, source_text: &str, source_lang: &str, target_lang: &str) -> Option<String> {
        let cleaned_text = source_text.trim();
        if cleaned_text.is_empty() {
            return None;
        }

        let src_l = source_lang.trim().to_lowercase();
        let tgt_l = target_lang.trim().to_lowercase();
        let now = Self::now_epoch_secs();

        let conn = self.conn.lock().ok()?;

        let mut stmt = conn
            .prepare(
                "SELECT translated_text FROM translations
                 WHERE source_text = ?1 AND source_lang = ?2 AND target_lang = ?3",
            )
            .ok()?;

        let row_result: SqlResult<String> = stmt.query_row(
            params![cleaned_text, src_l, tgt_l],
            |row| row.get(0),
        );

        match row_result {
            Ok(translated) => {
                // Non-fatal LRU update
                let _ = conn.execute(
                    "UPDATE translations
                     SET last_accessed = ?1, access_count = access_count + 1
                     WHERE source_text = ?2 AND source_lang = ?3 AND target_lang = ?4",
                    params![now, cleaned_text, src_l, tgt_l],
                );
                Some(translated)
            }
            Err(_) => None,
        }
    }

    /// Store translated text into cache, performing LRU pruning if limit is reached.
    pub fn set(
        &self,
        source_text: &str,
        source_lang: &str,
        target_lang: &str,
        translated_text: &str,
    ) {
        let cleaned_source = source_text.trim();
        let cleaned_trans = translated_text.trim();
        if cleaned_source.is_empty() || cleaned_trans.is_empty() {
            return;
        }

        let src_l = source_lang.trim().to_lowercase();
        let tgt_l = target_lang.trim().to_lowercase();
        let now = Self::now_epoch_secs();

        if let Ok(conn) = self.conn.lock() {
            let _ = conn.execute(
                "INSERT INTO translations (source_text, source_lang, target_lang, translated_text, access_count, last_accessed, created_at)
                 VALUES (?1, ?2, ?3, ?4, 1, ?5, ?5)
                 ON CONFLICT(source_text, source_lang, target_lang) DO UPDATE SET
                    translated_text = excluded.translated_text,
                    last_accessed = excluded.last_accessed,
                    access_count = translations.access_count + 1",
                params![cleaned_source, src_l, tgt_l, cleaned_trans, now],
            );

            // LRU capacity eviction check
            let count: i64 = conn
                .query_row("SELECT COUNT(*) FROM translations", [], |row| row.get(0))
                .unwrap_or(0);

            if count > self.max_entries as i64 {
                let excess = count - self.max_entries as i64;
                let _ = conn.execute(
                    "DELETE FROM translations WHERE (source_text, source_lang, target_lang) IN (
                         SELECT source_text, source_lang, target_lang FROM translations ORDER BY last_accessed ASC LIMIT ?1
                     )",
                    params![excess],
                );
            }
        }
    }

    /// Clear all stored translations from cache.
    pub fn clear(&self) -> SqlResult<()> {
        let conn = self.conn.lock().map_err(|_| rusqlite::Error::ExecuteReturnedResults)?;
        conn.execute("DELETE FROM translations", [])?;
        conn.execute("VACUUM", [])?;
        Ok(())
    }

    /// Return total number of cached entries.
    pub fn count(&self) -> usize {
        let conn = match self.conn.lock() {
            Ok(c) => c,
            Err(_) => return 0,
        };
        conn.query_row("SELECT COUNT(*) FROM translations", [], |row| row.get(0))
            .unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_miss_and_hit() {
        let cache = TranslationCache::open_in_memory().expect("open in-memory db");
        assert_eq!(cache.count(), 0);

        let miss = cache.get("Hello", "en", "id");
        assert!(miss.is_none());

        cache.set("Hello", "en", "id", "Halo");
        assert_eq!(cache.count(), 1);

        let hit = cache.get("Hello", "en", "id");
        assert_eq!(hit.as_deref(), Some("Halo"));

        // Case insensitivity of language codes
        let hit_upper = cache.get("Hello", "EN", "ID");
        assert_eq!(hit_upper.as_deref(), Some("Halo"));
    }

    #[test]
    fn test_cache_upsert_and_clear() {
        let cache = TranslationCache::open_in_memory().expect("open in-memory db");
        cache.set("Apple", "en", "id", "Apel");
        assert_eq!(cache.get("Apple", "en", "id").as_deref(), Some("Apel"));

        // Update translation
        cache.set("Apple", "en", "id", "Buah Apel");
        assert_eq!(cache.get("Apple", "en", "id").as_deref(), Some("Buah Apel"));
        assert_eq!(cache.count(), 1);

        cache.clear().expect("clear cache");
        assert_eq!(cache.count(), 0);
        assert!(cache.get("Apple", "en", "id").is_none());
    }

    #[test]
    fn test_cache_lru_eviction() {
        let mut cache = TranslationCache::open_in_memory().expect("open in-memory db");
        cache.max_entries = 5;

        for i in 1..=6 {
            cache.set(&format!("Text {}", i), "en", "id", &format!("Teks {}", i));
        }

        // Should have evicted oldest entries to stay around capacity
        assert!(cache.count() <= 5);
        assert!(cache.get("Text 6", "en", "id").is_some());
    }
}
