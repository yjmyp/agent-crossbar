use std::path::PathBuf;
use std::process::ExitCode;

use minisign_verify::{PublicKey, Signature};
use semver::Version;
use serde::Serialize;

#[derive(Debug)]
struct Arguments {
    artifact: PathBuf,
    signature: PathBuf,
    public_key: PathBuf,
    expected_version: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct VerificationResult {
    valid: bool,
    signed_version: String,
    expected_version: String,
    artifact_size_bytes: u64,
}

fn main() -> ExitCode {
    match run() {
        Ok(result) => {
            println!(
                "{}",
                serde_json::to_string(&result).expect("verification result should serialize")
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<VerificationResult, String> {
    let arguments = parse_arguments()?;
    let artifact =
        std::fs::read(&arguments.artifact).map_err(|error| format!("无法读取更新产物：{error}"))?;
    let public_key = PublicKey::from_file(&arguments.public_key)
        .map_err(|error| format!("无法读取 Minisign 公钥：{error}"))?;
    let signature = Signature::from_file(&arguments.signature)
        .map_err(|error| format!("无法读取 Minisign 签名：{error}"))?;

    public_key
        .verify(&artifact, &signature, true)
        .map_err(|error| format!("更新产物签名验证失败：{error}"))?;

    let trusted_comment = signature.trusted_comment();
    if let Some(signed_file) = trusted_comment_value(trusted_comment, "file:") {
        let artifact_file = arguments
            .artifact
            .file_name()
            .and_then(|value| value.to_str());
        if artifact_file != Some(signed_file) {
            return Err(format!(
                "更新签名绑定的是 {signed_file}，与当前产物文件名不一致。"
            ));
        }
    }
    let signed_version = trusted_comment_value(trusted_comment, "version:")
        .or_else(|| trusted_comment_value(trusted_comment, "app-version:"))
        .ok_or_else(|| "更新签名未绑定版本号。".to_owned())?;
    if !versions_match(signed_version, &arguments.expected_version) {
        return Err(format!(
            "更新签名版本 {signed_version} 与清单版本 {} 不一致。",
            arguments.expected_version
        ));
    }

    Ok(VerificationResult {
        valid: true,
        signed_version: signed_version.to_owned(),
        expected_version: arguments.expected_version,
        artifact_size_bytes: artifact.len() as u64,
    })
}

fn trusted_comment_value<'a>(comment: &'a str, prefix: &str) -> Option<&'a str> {
    comment
        .split_whitespace()
        .find_map(|part| part.strip_prefix(prefix))
}

fn versions_match(left: &str, right: &str) -> bool {
    match (
        Version::parse(left.trim_start_matches('v')),
        Version::parse(right.trim_start_matches('v')),
    ) {
        (Ok(left), Ok(right)) => left == right,
        _ => left == right,
    }
}

fn parse_arguments() -> Result<Arguments, String> {
    let mut artifact = None;
    let mut signature = None;
    let mut public_key = None;
    let mut expected_version = None;
    let mut iterator = std::env::args().skip(1);

    while let Some(argument) = iterator.next() {
        match argument.as_str() {
            "--artifact" => artifact = iterator.next().map(PathBuf::from),
            "--signature" => signature = iterator.next().map(PathBuf::from),
            "--public-key" => public_key = iterator.next().map(PathBuf::from),
            "--version" => expected_version = iterator.next(),
            "--help" | "-h" => {
                return Err(
                    "用法：verify-updater-signature --artifact <文件> --signature <文件> --public-key <文件> --version <版本>"
                        .to_owned(),
                );
            }
            value => {
                return Err(format!("未知参数：{value}"));
            }
        }
    }

    Ok(Arguments {
        artifact: artifact.ok_or_else(|| "缺少 --artifact。".to_owned())?,
        signature: signature.ok_or_else(|| "缺少 --signature。".to_owned())?,
        public_key: public_key.ok_or_else(|| "缺少 --public-key。".to_owned())?,
        expected_version: expected_version.ok_or_else(|| "缺少 --version。".to_owned())?,
    })
}

#[cfg(test)]
mod tests {
    use super::{trusted_comment_value, versions_match};

    #[test]
    fn semver_versions_allow_v_prefixes() {
        assert!(versions_match("v1.2.3", "1.2.3"));
        assert!(!versions_match("1.2.3", "1.2.4"));
    }

    #[test]
    fn non_semver_versions_require_exact_match() {
        assert!(versions_match("preview-7", "preview-7"));
        assert!(!versions_match("preview-7", "preview-8"));
    }

    #[test]
    fn trusted_comment_reads_tauri_file_and_version_fields() {
        let comment =
            "timestamp:1793691455\tfile:Agent-Crossbar.msi\tversion:0.1.0\tchannel:stable";

        assert_eq!(
            trusted_comment_value(comment, "file:"),
            Some("Agent-Crossbar.msi")
        );
        assert_eq!(trusted_comment_value(comment, "version:"), Some("0.1.0"));
        assert_eq!(trusted_comment_value(comment, "app-version:"), None);
    }
}
