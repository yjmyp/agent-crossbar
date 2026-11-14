import { mkdtemp, rm, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

const helperPath = path.resolve("scripts/build-installer.helpers.ps1");
const temporaryRoots = [];

afterEach(async () => {
  await Promise.all(
    temporaryRoots.splice(0).map((root) =>
      rm(root, { recursive: true, force: true }),
    ),
  );
});

async function createTemporaryRoot() {
  const root = await mkdtemp(path.join(tmpdir(), "agent-crossbar-release-"));
  temporaryRoots.push(root);
  return root;
}

function runPowerShell(script, ...arguments_) {
  const quotedArguments = arguments_
    .map((value) => `'${String(value).replaceAll("'", "''")}'`)
    .join(", ");
  const result = spawnSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-NonInteractive",
      "-ExecutionPolicy",
      "Bypass",
      "-Command",
      [
        '$ErrorActionPreference = "Stop"',
        `$releaseTestArguments = @(${quotedArguments})`,
        `. '${helperPath.replaceAll("'", "''")}' *> $null`,
        script,
      ].join("; "),
    ],
    {
      encoding: "utf8",
      windowsHide: true,
    },
  );

  if (result.status !== 0) {
    throw new Error(
      `PowerShell failed with ${result.status}\nSTDOUT:\n${result.stdout}\nSTDERR:\n${result.stderr}`,
    );
  }
  return result.stdout.trim();
}

describe("release artifact guards", () => {
  it("selects the sidecar for the exact host triple even when another triple is newer", async () => {
    const root = await createTemporaryRoot();
    const expectedName = "agent-crossbar-sidecar-x86_64-pc-windows-msvc.exe";
    const expectedPath = path.join(root, expectedName);
    const stalePath = path.join(
      root,
      "agent-crossbar-sidecar-aarch64-pc-windows-msvc.exe",
    );
    await writeFile(expectedPath, "expected");
    await new Promise((resolve) => setTimeout(resolve, 1100));
    await writeFile(stalePath, "newer but wrong architecture");

    const selected = runPowerShell(
      "$artifact = Select-SidecarArtifact -BinaryRoot $releaseTestArguments[0] -HostTriple 'x86_64-pc-windows-msvc'; $artifact.Name",
      root,
    );

    expect(selected).toBe(expectedName);
  });

  it("selects only the MSI created by the current bundle command", async () => {
    const root = await createTemporaryRoot();
    const existingPath = path.join(root, "Agent Crossbar_0.0.9_x64_en-US.msi");
    const createdPath = path.join(root, "Agent Crossbar_0.1.0_x64_en-US.msi");
    const unrelatedPath = path.join(root, "bundle.log");
    await writeFile(existingPath, "previous build");
    await writeFile(createdPath, "current build");
    await writeFile(unrelatedPath, "current build log");

    const now = Date.now();
    const buildStartedAt = new Date(now - 30_000);
    await utimes(existingPath, new Date(now - 60_000), new Date(now - 60_000));
    await utimes(createdPath, new Date(now - 10_000), new Date(now - 10_000));

    const result = JSON.parse(
      runPowerShell(
      [
        "$before = @($releaseTestArguments[1])",
        "$startedAt = [datetime]::Parse($releaseTestArguments[2], $null, [System.Globalization.DateTimeStyles]::RoundtripKind)",
        "$artifact = Select-SingleNewMsi -BundleDirectory $releaseTestArguments[0] -BeforePaths $before -BuildStartedAt $startedAt",
        "[pscustomobject]@{",
        "selected = $artifact.Name",
        "startedAt = $startedAt.ToString('o')",
        "msi = @(Get-ChildItem $releaseTestArguments[0] -Filter *.msi | ForEach-Object { $_.Name + '@' + $_.LastWriteTimeUtc.ToString('o') })",
        "} | ConvertTo-Json -Compress",
      ].join("\n"),
      root,
      existingPath,
        buildStartedAt.toISOString(),
      ),
    );

    expect(result.selected).toBe(path.basename(createdPath));
  });

  it("accepts one MSI overwritten by the current bundle command", async () => {
    const root = await createTemporaryRoot();
    const installerPath = path.join(
      root,
      "Agent Crossbar_0.1.0_x64_en-US.msi",
    );
    await writeFile(installerPath, "previous build");

    const now = Date.now();
    const buildStartedAt = new Date(now - 30_000);
    await writeFile(installerPath, "current build");
    await utimes(installerPath, new Date(now - 10_000), new Date(now - 10_000));

    const result = JSON.parse(
      runPowerShell(
      [
        "$before = @($releaseTestArguments[1])",
        "$startedAt = [datetime]::Parse($releaseTestArguments[2], $null, [System.Globalization.DateTimeStyles]::RoundtripKind)",
        "$artifact = Select-SingleNewMsi -BundleDirectory $releaseTestArguments[0] -BeforePaths $before -BuildStartedAt $startedAt",
        "[pscustomobject]@{",
        "selected = $artifact.Name",
        "startedAt = $startedAt.ToString('o')",
        "msi = @(Get-ChildItem $releaseTestArguments[0] -Filter *.msi | ForEach-Object { $_.Name + '@' + $_.LastWriteTimeUtc.ToString('o') })",
        "} | ConvertTo-Json -Compress",
      ].join("\n"),
      root,
      installerPath,
        buildStartedAt.toISOString(),
      ),
    );

    expect(result.selected).toBe(path.basename(installerPath));
  });

  it("resolves the inbox Windows PowerShell used for Authenticode inspection", () => {
    const resolved = runPowerShell(
      [
        "$resolved = Get-WindowsPowerShellPath",
        "[pscustomobject]@{",
        "name = [System.IO.Path]::GetFileName($resolved)",
        "exists = Test-Path -LiteralPath $resolved -PathType Leaf",
        "} | ConvertTo-Json -Compress",
      ].join("\n"),
    );

    expect(JSON.parse(resolved)).toEqual({
      name: "powershell.exe",
      exists: true,
    });
  });

  it("accepts a signing report only when every file carries the configured signer identity", () => {
    const accepted = runPowerShell(
      [
        "$report = [pscustomobject]@{",
        "status = 'signed'",
        "certificateThumbprint = 'AABB'",
        "certificateSubject = 'CN=Agent Crossbar Release'",
        "files = @(",
        "[pscustomobject]@{ valid = $true; thumbprint = 'aabb'; subject = 'CN=Agent Crossbar Release' },",
        "[pscustomobject]@{ valid = $true; thumbprint = 'AABB'; subject = 'CN=Agent Crossbar Release' }",
        ")",
        "}",
        "$result = Test-SigningReport -Report $report -ExpectedThumbprint 'AABB' -ExpectedSubject 'CN=Agent Crossbar Release'",
        '$result.ToString().ToLowerInvariant()',
      ].join("\n"),
    );

    expect(accepted).toBe("true");
  });

  it("rejects a written release manifest when an artifact hash changed", async () => {
    const root = await createTemporaryRoot();
    const artifactPath = path.join(root, "agent-crossbar.exe");
    await writeFile(artifactPath, "changed after hashing");
    const artifactSize = (await stat(artifactPath)).size;

    expect(() =>
      runPowerShell(
        [
          "$manifest = [pscustomobject]@{",
          "installer = [pscustomobject]@{",
          "path = $releaseTestArguments[0]",
          `sizeBytes = ${artifactSize}`,
          "sha256 = '0000000000000000000000000000000000000000000000000000000000000000'",
          "}",
          "desktopBinary = [pscustomobject]@{",
          "path = $releaseTestArguments[0]",
          `sizeBytes = ${artifactSize}`,
          "sha256 = '0000000000000000000000000000000000000000000000000000000000000000'",
          "}",
          "sidecarBinary = [pscustomobject]@{",
          "path = $releaseTestArguments[0]",
          `sizeBytes = ${artifactSize}`,
          "sha256 = '0000000000000000000000000000000000000000000000000000000000000000'",
          "}",
          "}",
          "Assert-ReleaseManifestIntegrity -Manifest $manifest",
        ].join("\n"),
        artifactPath,
      ),
    ).toThrow(/SHA-256/i);
  });
});
