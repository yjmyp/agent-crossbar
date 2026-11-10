use std::path::Path;
use std::process::Command;

use base64::Engine;
use serde::{Deserialize, Serialize};
use tauri::AppHandle;
use tauri_plugin_updater::{Update, Updater, UpdaterExt};
use url::Url;

const UPDATE_ENDPOINTS_ENV: &str = "AGENT_CROSSBAR_UPDATE_ENDPOINTS";
const UPDATE_PUBKEY_ENV: &str = "AGENT_CROSSBAR_UPDATE_PUBKEY";

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SignatureStatus {
    status: String,
    valid: bool,
    subject: Option<String>,
    thumbprint: Option<String>,
    message: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateStatus {
    configured: bool,
    available: bool,
    current_version: String,
    version: Option<String>,
    date: Option<String>,
    body: Option<String>,
    message: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInstallResult {
    started: bool,
    restart_recommended: bool,
    message: String,
}

#[derive(Debug, Deserialize)]
struct SignatureProbe {
    status: String,
    valid: bool,
    subject: Option<String>,
    thumbprint: Option<String>,
}

struct UpdateConfiguration {
    endpoints: Vec<Url>,
    pubkey: String,
}

fn update_configuration() -> Result<Option<UpdateConfiguration>, String> {
    parse_update_configuration_with_policy(
        &std::env::var(UPDATE_ENDPOINTS_ENV).unwrap_or_default(),
        &std::env::var(UPDATE_PUBKEY_ENV).unwrap_or_default(),
        !cfg!(debug_assertions),
    )
}

#[cfg(test)]
fn parse_update_configuration(
    endpoints_value: &str,
    pubkey: &str,
) -> Result<Option<UpdateConfiguration>, String> {
    parse_update_configuration_with_policy(endpoints_value, pubkey, false)
}

fn parse_update_configuration_with_policy(
    endpoints_value: &str,
    pubkey: &str,
    require_https: bool,
) -> Result<Option<UpdateConfiguration>, String> {
    let endpoints_value = endpoints_value.trim();
    let pubkey = pubkey.trim();

    if endpoints_value.is_empty() && pubkey.is_empty() {
        return Ok(None);
    }
    if endpoints_value.is_empty() || pubkey.is_empty() {
        return Err("更新地址和更新公钥必须同时配置。".to_owned());
    }

    let endpoints = endpoints_value
        .split([';', ',', '\n', '\r'])
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|value| {
            let endpoint = Url::parse(value).map_err(|error| format!("更新地址无效：{error}"))?;
            validate_update_endpoint(&endpoint, require_https)?;
            Ok::<Url, String>(endpoint)
        })
        .collect::<Result<Vec<_>, _>>()?;
    if endpoints.is_empty() {
        return Err("更新地址为空。".to_owned());
    }

    let pubkey =
        normalize_update_public_key(pubkey).map_err(|error| format!("更新公钥无效：{error}"))?;

    Ok(Some(UpdateConfiguration { endpoints, pubkey }))
}

fn validate_update_endpoint(endpoint: &Url, require_https: bool) -> Result<(), String> {
    if !endpoint.username().is_empty() || endpoint.password().is_some() {
        return Err("更新地址不能包含用户名或密码。".to_owned());
    }
    if endpoint.fragment().is_some() {
        return Err("更新地址不能包含片段标识。".to_owned());
    }
    if endpoint.scheme() != "https" {
        let development_loopback = !require_https
            && endpoint.scheme() == "http"
            && endpoint
                .host_str()
                .is_some_and(|host| matches!(host, "127.0.0.1" | "::1" | "localhost"));
        if !development_loopback {
            return Err("发布版更新地址必须使用 HTTPS。".to_owned());
        }
    }
    Ok(())
}

fn normalize_update_public_key(pubkey: &str) -> Result<String, String> {
    let trimmed = pubkey.trim();
    if trimmed.is_empty() {
        return Err("公钥为空。".to_owned());
    }

    if minisign_verify::PublicKey::decode(trimmed).is_ok() {
        return Ok(base64::engine::general_purpose::STANDARD.encode(trimmed.as_bytes()));
    }

    let decoded = base64::engine::general_purpose::STANDARD
        .decode(trimmed)
        .or_else(|_| base64::engine::general_purpose::STANDARD_NO_PAD.decode(trimmed))
        .map_err(|_| "公钥必须是 Tauri 公钥文件内容或其 Base64 编码。".to_owned())?;
    let decoded_text =
        String::from_utf8(decoded).map_err(|_| "公钥 Base64 解码后不是 UTF-8 文本。".to_owned())?;
    minisign_verify::PublicKey::decode(decoded_text.trim())
        .map_err(|error| format!("Minisign 公钥格式错误：{error}"))?;
    Ok(trimmed.to_owned())
}

fn updater(app: &AppHandle, configuration: UpdateConfiguration) -> Result<Updater, String> {
    app.updater_builder()
        .endpoints(configuration.endpoints)
        .map_err(|error| format!("更新地址无效：{error}"))?
        .pubkey(configuration.pubkey)
        // Keep the decision explicit even though the static plugin configuration also
        // disables downgrades. A signed older release must never be installed.
        .version_comparator(|current, release| is_newer_release(&current, &release.version))
        .build()
        .map_err(|error| format!("无法初始化更新器：{error}"))
}

fn is_newer_release(current: &semver::Version, release: &semver::Version) -> bool {
    release > current
}

async fn checked_update(app: &AppHandle) -> Result<(UpdateConfiguration, Option<Update>), String> {
    let configuration = update_configuration()?.ok_or_else(|| "更新服务未配置。".to_owned())?;
    let update = updater(
        app,
        UpdateConfiguration {
            endpoints: configuration.endpoints.clone(),
            pubkey: configuration.pubkey.clone(),
        },
    )?
    .check()
    .await
    .map_err(|error| format!("检查更新失败：{error}"))?;
    Ok((configuration, update))
}

#[tauri::command]
pub fn get_signature_status() -> SignatureStatus {
    let executable = match std::env::current_exe() {
        Ok(path) => path,
        Err(error) => {
            return unavailable_signature(format!("无法定位当前程序：{error}"));
        }
    };
    signature_status(&executable)
}

#[tauri::command]
pub async fn get_update_status(app: AppHandle) -> Result<UpdateStatus, String> {
    let current_version = app.package_info().version.to_string();
    let configuration = match update_configuration() {
        Ok(Some(configuration)) => configuration,
        Ok(None) => {
            return Ok(UpdateStatus {
                configured: false,
                available: false,
                current_version,
                version: None,
                date: None,
                body: None,
                message: "更新服务未配置。".to_owned(),
            });
        }
        Err(error) => {
            return Ok(UpdateStatus {
                configured: true,
                available: false,
                current_version,
                version: None,
                date: None,
                body: None,
                message: error,
            });
        }
    };

    let update = updater(&app, configuration)?
        .check()
        .await
        .map_err(|error| format!("检查更新失败：{error}"))?;
    let message = if update.is_some() {
        "发现可用更新。安装包将在下载后由配置的公钥验证。".to_owned()
    } else {
        "当前已是最新版本。".to_owned()
    };
    Ok(UpdateStatus {
        configured: true,
        available: update.is_some(),
        current_version,
        version: update.as_ref().map(|value| value.version.clone()),
        date: update
            .as_ref()
            .and_then(|value| value.date.map(|date| date.to_string())),
        body: update.and_then(|value| value.body),
        message,
    })
}

#[tauri::command]
pub async fn install_update(app: AppHandle) -> Result<UpdateInstallResult, String> {
    let (_, update) = match checked_update(&app).await {
        Ok(result) => result,
        Err(error) if error == "更新服务未配置。" => {
            return Ok(UpdateInstallResult {
                started: false,
                restart_recommended: false,
                message: error,
            });
        }
        Err(error) => return Err(error),
    };
    let update = update.ok_or_else(|| "当前没有可用更新。".to_owned())?;
    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|error| format!("下载或启动安装程序失败：{error}"))?;

    #[cfg(windows)]
    let restart_recommended = false;
    #[cfg(not(windows))]
    let restart_recommended = true;

    Ok(UpdateInstallResult {
        started: true,
        restart_recommended,
        message: if cfg!(windows) {
            "安装程序已启动。应用退出后由安装程序完成更新并重新启动。".to_owned()
        } else {
            "安装程序已启动。安装完成后请重启应用。".to_owned()
        },
    })
}

#[tauri::command]
pub fn restart_application(app: AppHandle) {
    app.request_restart();
}

fn unavailable_signature(message: String) -> SignatureStatus {
    SignatureStatus {
        status: "Unavailable".to_owned(),
        valid: false,
        subject: None,
        thumbprint: None,
        message,
    }
}

#[cfg(windows)]
fn signature_status(executable: &Path) -> SignatureStatus {
    use std::os::windows::process::CommandExt;

    const CREATE_NO_WINDOW: u32 = 0x08000000;
    const PROBE_SCRIPT: &str = r#"
$ErrorActionPreference = "Stop"
$target = $env:AGENT_CROSSBAR_SIGNATURE_TARGET
$signature = Get-AuthenticodeSignature -LiteralPath $target
$certificate = $signature.SignerCertificate
[pscustomobject]@{
  status = $signature.Status.ToString()
  valid = ($signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid)
  subject = if ($null -eq $certificate) { $null } else { $certificate.Subject }
  thumbprint = if ($null -eq $certificate) { $null } else { $certificate.Thumbprint }
} | ConvertTo-Json -Compress
"#;
    let encoded = encode_powershell(PROBE_SCRIPT);
    let output = match Command::new("powershell.exe")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            &encoded,
        ])
        .env("AGENT_CROSSBAR_SIGNATURE_TARGET", executable)
        .creation_flags(CREATE_NO_WINDOW)
        .output()
    {
        Ok(output) => output,
        Err(error) => {
            return unavailable_signature(format!("无法启动 Authenticode 验证：{error}"));
        }
    };
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return unavailable_signature(if detail.is_empty() {
            "Authenticode 验证进程失败。".to_owned()
        } else {
            format!("Authenticode 验证进程失败：{detail}")
        });
    }
    let probe = match serde_json::from_slice::<SignatureProbe>(&output.stdout) {
        Ok(probe) => probe,
        Err(error) => {
            return unavailable_signature(format!("无法解析 Authenticode 结果：{error}"));
        }
    };
    let message = match probe.status.as_str() {
        "Valid" => "当前程序已通过 Windows Authenticode 验证。",
        "NotSigned" => "当前程序没有 Windows Authenticode 签名。",
        "HashMismatch" => "当前文件哈希与 Authenticode 签名不匹配。",
        "NotTrusted" => "当前程序签名证书不受系统信任。",
        "UnknownError" => "Windows 无法验证当前程序的 Authenticode 签名。",
        _ => "当前程序签名状态不可用于生产发布。",
    };
    SignatureStatus {
        status: probe.status,
        valid: probe.valid,
        subject: probe.subject,
        thumbprint: probe.thumbprint,
        message: message.to_owned(),
    }
}

#[cfg(not(windows))]
fn signature_status(_executable: &Path) -> SignatureStatus {
    unavailable_signature("当前平台不支持 Windows Authenticode 验证。".to_owned())
}

#[cfg(windows)]
fn encode_powershell(script: &str) -> String {
    use base64::Engine;

    let utf16 = script
        .encode_utf16()
        .flat_map(u16::to_le_bytes)
        .collect::<Vec<_>>();
    base64::engine::general_purpose::STANDARD.encode(utf16)
}

#[cfg(test)]
mod tests {
    use super::{
        is_newer_release, parse_update_configuration, parse_update_configuration_with_policy,
    };
    use base64::Engine;

    const PUBLIC_KEY: &str = concat!(
        "untrusted comment: minisign public key\n",
        "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3"
    );

    #[test]
    fn update_configuration_is_disabled_when_both_values_are_empty() {
        assert!(parse_update_configuration("", "").unwrap().is_none());
    }

    #[test]
    fn update_configuration_rejects_partial_configuration() {
        let endpoint_error =
            match parse_update_configuration("https://updates.example.test/latest.json", "") {
                Ok(_) => panic!("partial update configuration should be rejected"),
                Err(error) => error,
            };
        assert_eq!(endpoint_error, "更新地址和更新公钥必须同时配置。");

        let key_error = match parse_update_configuration("", PUBLIC_KEY) {
            Ok(_) => panic!("partial update configuration should be rejected"),
            Err(error) => error,
        };
        assert_eq!(key_error, "更新地址和更新公钥必须同时配置。");
    }

    #[test]
    fn update_configuration_accepts_multiple_endpoint_separators() {
        let configuration = parse_update_configuration(
            "https://primary.example.test/latest.json;\n https://backup.example.test/latest.json ",
            PUBLIC_KEY,
        )
        .unwrap()
        .unwrap();

        assert_eq!(configuration.endpoints.len(), 2);
        assert_eq!(
            configuration.endpoints[0].as_str(),
            "https://primary.example.test/latest.json"
        );
        assert_eq!(
            configuration.endpoints[1].as_str(),
            "https://backup.example.test/latest.json"
        );
        assert_eq!(
            base64::engine::general_purpose::STANDARD
                .decode(&configuration.pubkey)
                .unwrap(),
            PUBLIC_KEY.as_bytes()
        );
    }

    #[test]
    fn update_configuration_rejects_an_endpoint_list_without_urls() {
        let error = match parse_update_configuration(" ; , \n ", PUBLIC_KEY) {
            Ok(_) => panic!("empty endpoint list should be rejected"),
            Err(error) => error,
        };
        assert_eq!(error, "更新地址为空。");
        assert!(!error.contains(PUBLIC_KEY));
    }

    #[test]
    fn update_configuration_reports_invalid_urls_without_exposing_the_public_key() {
        let error = match parse_update_configuration("not-a-url", PUBLIC_KEY) {
            Ok(_) => panic!("invalid endpoint should be rejected"),
            Err(error) => error,
        };
        assert!(error.starts_with("更新地址无效："));
        assert!(!error.contains("minisign public key"));
    }

    #[test]
    fn production_update_configuration_rejects_http_even_for_loopback() {
        let error = match parse_update_configuration_with_policy(
            "http://127.0.0.1:8080/latest.json",
            PUBLIC_KEY,
            true,
        ) {
            Ok(_) => panic!("release configuration should reject HTTP"),
            Err(error) => error,
        };
        assert_eq!(error, "发布版更新地址必须使用 HTTPS。");
    }

    #[test]
    fn development_update_configuration_allows_only_loopback_http() {
        assert!(
            parse_update_configuration_with_policy(
                "http://127.0.0.1:8080/latest.json",
                PUBLIC_KEY,
                false,
            )
            .is_ok()
        );
        let error = match parse_update_configuration_with_policy(
            "http://updates.example.test/latest.json",
            PUBLIC_KEY,
            false,
        ) {
            Ok(_) => panic!("non-loopback HTTP should be rejected"),
            Err(error) => error,
        };
        assert_eq!(error, "发布版更新地址必须使用 HTTPS。");
    }

    #[test]
    fn update_endpoint_rejects_embedded_credentials_and_fragments() {
        let credentials_error = match parse_update_configuration(
            "https://user:secret@updates.example.test/latest.json",
            PUBLIC_KEY,
        ) {
            Ok(_) => panic!("endpoint credentials should be rejected"),
            Err(error) => error,
        };
        assert_eq!(credentials_error, "更新地址不能包含用户名或密码。");

        let fragment_error = match parse_update_configuration(
            "https://updates.example.test/latest.json#fragment",
            PUBLIC_KEY,
        ) {
            Ok(_) => panic!("endpoint fragments should be rejected"),
            Err(error) => error,
        };
        assert_eq!(fragment_error, "更新地址不能包含片段标识。");
    }

    #[test]
    fn update_public_key_accepts_tauri_base64_encoding() {
        let encoded = base64::engine::general_purpose::STANDARD.encode(PUBLIC_KEY.as_bytes());
        let configuration =
            parse_update_configuration("https://updates.example.test/latest.json", &encoded)
                .unwrap()
                .unwrap();
        assert_eq!(configuration.pubkey, encoded);
    }

    #[test]
    fn update_configuration_rejects_malformed_public_keys() {
        let error = match parse_update_configuration(
            "https://updates.example.test/latest.json",
            "this-is-not-a-minisign-key",
        ) {
            Ok(_) => panic!("malformed public key should be rejected"),
            Err(error) => error,
        };
        assert!(error.starts_with("更新公钥无效："));
    }

    #[test]
    fn updater_accepts_only_strictly_newer_versions() {
        let current = semver::Version::parse("1.4.2").unwrap();
        let older = semver::Version::parse("1.4.1").unwrap();
        let equal = semver::Version::parse("1.4.2").unwrap();
        let newer = semver::Version::parse("1.4.3").unwrap();

        assert!(!is_newer_release(&current, &older));
        assert!(!is_newer_release(&current, &equal));
        assert!(is_newer_release(&current, &newer));
    }
}
