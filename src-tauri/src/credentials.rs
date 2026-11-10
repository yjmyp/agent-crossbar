use keyring::{Entry, Error as KeyringError};
use serde::{Deserialize, Serialize};
use url::Url;

const SERVICE: &str = "com.agentcrossbar.desktop.openai";
const ACCOUNT: &str = "openai.default";
const EMBEDDING_SERVICE: &str = "com.agentcrossbar.desktop.embedding";
const EMBEDDING_ACCOUNT: &str = "embedding.default";
const STORAGE_LABEL: &str = "Windows Credential Manager";
const MAX_BASE_URL_CHARS: usize = 2_048;
const MAX_API_KEY_CHARS: usize = 4_096;
const MAX_MODEL_CHARS: usize = 200;
const MAX_ENCODED_CREDENTIAL_BYTES: usize = 2_400;

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProviderCredentialInput {
    base_url: String,
    api_key: String,
    model: String,
}

#[derive(Clone, Deserialize, Serialize)]
pub struct StoredProviderCredential {
    base_url: String,
    api_key: String,
    model: String,
}

impl std::fmt::Debug for StoredProviderCredential {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("StoredProviderCredential")
            .field("base_url", &self.base_url)
            .field("api_key", &"[REDACTED]")
            .field("model", &self.model)
            .finish()
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderCredentialSummary {
    configured: bool,
    base_url: Option<String>,
    model: Option<String>,
    storage: &'static str,
}

impl StoredProviderCredential {
    fn summary(&self) -> ProviderCredentialSummary {
        ProviderCredentialSummary {
            configured: true,
            base_url: Some(self.base_url.clone()),
            model: Some(self.model.clone()),
            storage: STORAGE_LABEL,
        }
    }
}

pub fn summary() -> Result<ProviderCredentialSummary, String> {
    Ok(match read_stored()? {
        Some(stored) => stored.summary(),
        None => ProviderCredentialSummary {
            configured: false,
            base_url: None,
            model: None,
            storage: STORAGE_LABEL,
        },
    })
}

pub fn save(input: ProviderCredentialInput) -> Result<ProviderCredentialSummary, String> {
    let stored = validate_input(input)?;
    let encoded = serde_json::to_string(&stored)
        .map_err(|_| "The model connection could not be encoded.".to_string())?;
    entry()?.set_password(&encoded).map_err(|_| {
        "The operating system credential store could not save the connection.".to_string()
    })?;
    Ok(stored.summary())
}

pub fn delete() -> Result<(), String> {
    delete_at(SERVICE, ACCOUNT)
}

pub fn embedding_summary() -> Result<ProviderCredentialSummary, String> {
    summary_at(EMBEDDING_SERVICE, EMBEDDING_ACCOUNT)
}

pub fn save_embedding(input: ProviderCredentialInput) -> Result<ProviderCredentialSummary, String> {
    save_at(EMBEDDING_SERVICE, EMBEDDING_ACCOUNT, input)
}

pub fn delete_embedding() -> Result<(), String> {
    delete_at(EMBEDDING_SERVICE, EMBEDDING_ACCOUNT)
}

fn summary_at(service: &str, account: &str) -> Result<ProviderCredentialSummary, String> {
    Ok(match read_stored_at(service, account)? {
        Some(stored) => stored.summary(),
        None => ProviderCredentialSummary {
            configured: false,
            base_url: None,
            model: None,
            storage: STORAGE_LABEL,
        },
    })
}

fn save_at(
    service: &str,
    account: &str,
    input: ProviderCredentialInput,
) -> Result<ProviderCredentialSummary, String> {
    let stored = validate_input(input)?;
    let encoded = serde_json::to_string(&stored)
        .map_err(|_| "The model connection could not be encoded.".to_string())?;
    entry_at(service, account)?
        .set_password(&encoded)
        .map_err(|_| {
            "The operating system credential store could not save the connection.".to_string()
        })?;
    Ok(stored.summary())
}

fn delete_at(service: &str, account: &str) -> Result<(), String> {
    match entry_at(service, account)?.delete_credential() {
        Ok(()) | Err(KeyringError::NoEntry) => Ok(()),
        Err(_) => Err(
            "The operating system credential store could not remove the connection.".to_string(),
        ),
    }
}

pub fn sidecar_environment() -> Result<Vec<(String, String)>, String> {
    read_stored_at(SERVICE, ACCOUNT).map(environment_for)
}

pub fn embedding_sidecar_environment() -> Result<Vec<(String, String)>, String> {
    read_stored_at(EMBEDDING_SERVICE, EMBEDDING_ACCOUNT).map(embedding_environment_for)
}

fn validate_input(input: ProviderCredentialInput) -> Result<StoredProviderCredential, String> {
    let base_url = input.base_url.trim().trim_end_matches('/').to_string();
    let api_key = input.api_key.trim().to_string();
    let model = input.model.trim().to_string();

    if base_url.is_empty()
        || base_url.chars().count() > MAX_BASE_URL_CHARS
        || api_key.is_empty()
        || api_key.chars().count() > MAX_API_KEY_CHARS
        || model.is_empty()
        || model.chars().count() > MAX_MODEL_CHARS
    {
        return Err(
            "Base URL, API key, and model are required and must be within the supported size."
                .to_string(),
        );
    }

    let parsed = Url::parse(&base_url)
        .map_err(|_| "Base URL must be a complete HTTP(S) address with a host.".to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") || parsed.host_str().is_none() {
        return Err("Base URL must be a complete HTTP(S) address with a host.".to_string());
    }
    if parsed.query().is_some() || parsed.fragment().is_some() {
        return Err("Base URL must not contain a query or fragment.".to_string());
    }
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err("Base URL must not embed credentials.".to_string());
    }
    if parsed.scheme() == "http" && !is_loopback_host(parsed.host_str().unwrap_or_default()) {
        return Err("Base URL must use HTTPS outside loopback development.".to_string());
    }

    let stored = StoredProviderCredential {
        base_url,
        api_key,
        model,
    };
    let encoded_size = serde_json::to_vec(&stored)
        .map_err(|_| "The model connection could not be encoded.".to_string())?
        .len();
    if encoded_size > MAX_ENCODED_CREDENTIAL_BYTES {
        return Err(
            "The model connection is too large for Windows Credential Manager.".to_string(),
        );
    }
    Ok(stored)
}

fn is_loopback_host(host: &str) -> bool {
    if host.eq_ignore_ascii_case("localhost") {
        return true;
    }
    host.parse::<std::net::IpAddr>()
        .map(|address| address.is_loopback())
        .unwrap_or(false)
}

fn environment_for(stored: Option<StoredProviderCredential>) -> Vec<(String, String)> {
    let Some(stored) = stored else {
        return Vec::new();
    };
    vec![
        (
            "AGENT_CROSSBAR_OPENAI_BASE_URL".to_string(),
            stored.base_url,
        ),
        ("AGENT_CROSSBAR_OPENAI_API_KEY".to_string(), stored.api_key),
        ("AGENT_CROSSBAR_OPENAI_MODEL".to_string(), stored.model),
    ]
}

fn read_stored() -> Result<Option<StoredProviderCredential>, String> {
    read_stored_at(SERVICE, ACCOUNT)
}

fn read_stored_at(
    service: &str,
    account: &str,
) -> Result<Option<StoredProviderCredential>, String> {
    let encoded = match entry_at(service, account)?.get_password() {
        Ok(value) => value,
        Err(KeyringError::NoEntry) => return Ok(None),
        Err(_) => {
            return Err(
                "The operating system credential store could not read the connection.".to_string(),
            );
        }
    };
    serde_json::from_str(&encoded).map(Some).map_err(|_| {
        "The stored model connection is invalid. Re-enter the connection details.".to_string()
    })
}

fn entry() -> Result<Entry, String> {
    entry_at(SERVICE, ACCOUNT)
}

fn entry_at(service: &str, account: &str) -> Result<Entry, String> {
    Entry::new(service, account)
        .map_err(|_| "The operating system credential store is unavailable.".to_string())
}

fn embedding_environment_for(stored: Option<StoredProviderCredential>) -> Vec<(String, String)> {
    let Some(stored) = stored else {
        return Vec::new();
    };
    vec![
        (
            "AGENT_CROSSBAR_EMBEDDING_BASE_URL".to_string(),
            stored.base_url,
        ),
        (
            "AGENT_CROSSBAR_EMBEDDING_API_KEY".to_string(),
            stored.api_key,
        ),
        ("AGENT_CROSSBAR_EMBEDDING_MODEL".to_string(), stored.model),
    ]
}

#[cfg(test)]
mod tests {
    use super::{ProviderCredentialInput, StoredProviderCredential, validate_input};

    fn input(base_url: &str, model: &str, api_key: &str) -> ProviderCredentialInput {
        ProviderCredentialInput {
            base_url: base_url.to_string(),
            api_key: api_key.to_string(),
            model: model.to_string(),
        }
    }

    #[test]
    fn rejects_non_http_provider_urls() {
        let error = validate_input(input("file:///secret", "model-a", "key")).unwrap_err();
        assert!(error.contains("HTTP"));
        assert!(!error.contains("secret"));
    }

    #[test]
    fn rejects_urls_that_embed_credentials() {
        let error = validate_input(input(
            "https://user:secret@model.example/v1",
            "model-a",
            "key",
        ))
        .unwrap_err();
        assert!(error.contains("credentials"));
        assert!(!error.contains("secret"));
    }

    #[test]
    fn rejects_plain_http_outside_loopback() {
        let error = validate_input(input("http://model.example/v1", "model-a", "key")).unwrap_err();
        assert!(error.contains("HTTPS"));
    }

    #[test]
    fn accepts_plain_http_on_loopback() {
        let stored = validate_input(input("http://127.0.0.1:8080/v1", "model-a", "key")).unwrap();
        assert_eq!(stored.base_url, "http://127.0.0.1:8080/v1");
    }

    #[test]
    fn summary_does_not_contain_the_api_key() {
        let stored = StoredProviderCredential {
            base_url: "https://model.example/v1".to_string(),
            api_key: "must-not-leak".to_string(),
            model: "model-a".to_string(),
        };

        let encoded = serde_json::to_string(&stored.summary()).unwrap();

        assert!(!encoded.contains("must-not-leak"));
        assert!(encoded.contains("model-a"));
        assert!(encoded.contains("Windows Credential Manager"));
    }

    #[test]
    fn debug_output_does_not_contain_the_api_key() {
        let stored = StoredProviderCredential {
            base_url: "https://model.example/v1".to_string(),
            api_key: "must-not-leak".to_string(),
            model: "model-a".to_string(),
        };

        let debug = format!("{stored:?}");

        assert!(!debug.contains("must-not-leak"));
        assert!(debug.contains("[REDACTED]"));
    }

    #[test]
    fn sidecar_environment_is_explicit_and_contains_no_command_line_values() {
        let stored = StoredProviderCredential {
            base_url: "https://model.example/v1".to_string(),
            api_key: "test-secret".to_string(),
            model: "model-a".to_string(),
        };

        let environment = super::environment_for(Some(stored));

        assert_eq!(
            environment,
            vec![
                (
                    "AGENT_CROSSBAR_OPENAI_BASE_URL".to_string(),
                    "https://model.example/v1".to_string(),
                ),
                (
                    "AGENT_CROSSBAR_OPENAI_API_KEY".to_string(),
                    "test-secret".to_string(),
                ),
                (
                    "AGENT_CROSSBAR_OPENAI_MODEL".to_string(),
                    "model-a".to_string(),
                ),
            ]
        );
        assert!(super::environment_for(None).is_empty());
    }

    #[test]
    fn embedding_environment_uses_a_distinct_prefix() {
        let stored = StoredProviderCredential {
            base_url: "https://embedding.example/v1".to_string(),
            api_key: "embedding-secret".to_string(),
            model: "embedding-a".to_string(),
        };

        let environment = super::embedding_environment_for(Some(stored));

        assert_eq!(
            environment,
            vec![
                (
                    "AGENT_CROSSBAR_EMBEDDING_BASE_URL".to_string(),
                    "https://embedding.example/v1".to_string(),
                ),
                (
                    "AGENT_CROSSBAR_EMBEDDING_API_KEY".to_string(),
                    "embedding-secret".to_string(),
                ),
                (
                    "AGENT_CROSSBAR_EMBEDDING_MODEL".to_string(),
                    "embedding-a".to_string(),
                ),
            ]
        );
        assert!(super::embedding_environment_for(None).is_empty());
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn windows_credential_manager_round_trip_uses_the_native_store() {
        use keyring::{Entry, Error};

        let account = format!("round-trip-{}", uuid::Uuid::new_v4().simple());
        let entry = Entry::new("com.agentcrossbar.desktop.openai.tests", &account).unwrap();

        entry.set_password("must-not-leak").unwrap();
        assert_eq!(entry.get_password().unwrap(), "must-not-leak");
        entry.delete_credential().unwrap();
        assert!(matches!(entry.get_password(), Err(Error::NoEntry)));
        assert!(matches!(entry.delete_credential(), Err(Error::NoEntry)));
    }
}
