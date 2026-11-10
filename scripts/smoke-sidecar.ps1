$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$smokeRoot = Join-Path $projectRoot ".build\sidecar-smoke"
$runtimeTemp = Join-Path $smokeRoot "runtime-temp"
$databasePath = Join-Path $smokeRoot "smoke.db"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mockProviderScript = Join-Path $projectRoot "scripts\mock-openai-server.py"
$mcpFixture = Join-Path $projectRoot "backend\tests\fixtures\mcp_echo_server.py"
$rustcCommand = Get-Command rustc -ErrorAction SilentlyContinue
$rustc = if ($rustcCommand) {
    $rustcCommand.Source
} else {
    Join-Path $env:USERPROFILE ".cargo\bin\rustc.exe"
}
if (-not (Test-Path -LiteralPath $rustc)) {
    throw "rustc is missing. Install the Rust toolchain before running the sidecar smoke test."
}
$targetTriple = (& $rustc --print host-tuple).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "rustc failed while resolving the host target."
}
$binaryPath = Join-Path `
    $projectRoot `
    "src-tauri\binaries\agent-crossbar-sidecar-$targetTriple.exe"

function Get-Sha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string] $LiteralPath
    )

    $stream = [System.IO.File]::OpenRead($LiteralPath)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $bytes = $sha256.ComputeHash($stream)
        } finally {
            $sha256.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
    return ([BitConverter]::ToString($bytes) -replace "-", "").ToUpperInvariant()
}

function Invoke-Utf8Json {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Uri,
        [string] $Method = "Get",
        [hashtable] $Headers = @{},
        [string] $ContentType,
        [string] $Body
    )

    $request = @{
        Uri = $Uri
        Method = $Method
        Headers = $Headers
        UseBasicParsing = $true
    }
    if ($ContentType) {
        $request.ContentType = $ContentType
    }
    if ($Body) {
        $request.Body = $Body
    }
    $response = Invoke-WebRequest @request
    $bytes = $response.RawContentStream.ToArray()
    $json = [System.Text.Encoding]::UTF8.GetString($bytes)
    $parsed = $json | ConvertFrom-Json
    if ($parsed -is [System.Array]) {
        $parsed | ForEach-Object { $_ }
        return
    }
    return $parsed
}

function New-RandomHex {
    param([int] $ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return ([BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
}

function Wait-ForReadyLine {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process] $Process,
        [Parameter(Mandatory = $true)]
        [string] $StdoutPath,
        [Parameter(Mandatory = $true)]
        [string] $StderrPath,
        [int] $TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        if ($Process.HasExited) {
            $stderr = Get-Content -LiteralPath $StderrPath -Raw -ErrorAction SilentlyContinue
            throw "Process $($Process.Id) exited with code $($Process.ExitCode): $stderr"
        }
        if (Test-Path -LiteralPath $StdoutPath) {
            $line = Get-Content -LiteralPath $StdoutPath -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($line) {
                return ($line | ConvertFrom-Json)
            }
        }
    }
    throw "Process $($Process.Id) did not publish a ready line within $TimeoutSeconds seconds."
}

function Start-MockProvider {
    param(
        [Parameter(Mandatory = $true)]
        [string] $StdoutPath,
        [Parameter(Mandatory = $true)]
        [string] $StderrPath
    )

    $process = Start-Process `
        -FilePath $python `
        -ArgumentList @($mockProviderScript, "--port", "0") `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -WindowStyle Hidden `
        -PassThru
    $ready = Wait-ForReadyLine `
        -Process $process `
        -StdoutPath $StdoutPath `
        -StderrPath $StderrPath `
        -TimeoutSeconds 20
    return [pscustomobject]@{
        Process = $process
        Port = [int]$ready.port
    }
}

function Start-Sidecar {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Token,
        [Parameter(Mandatory = $true)]
        [string] $StdoutPath,
        [Parameter(Mandatory = $true)]
        [string] $StderrPath
    )

    $parentProcessId = $PID
    $process = Start-Process `
        -FilePath $binaryPath `
        -ArgumentList @(
            "--database",
            $databasePath,
            "--token",
            $Token,
            "--port",
            "0",
            "--parent-pid",
            "$parentProcessId"
        ) `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -WindowStyle Hidden `
        -PassThru
    $handshake = Wait-ForReadyLine `
        -Process $process `
        -StdoutPath $StdoutPath `
        -StderrPath $StderrPath
    return [pscustomobject]@{
        Process = $process
        BaseUrl = "http://127.0.0.1:$($handshake.port)"
    }
}

function Wait-Run {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BaseUrl,
        [Parameter(Mandatory = $true)]
        [hashtable] $Headers,
        [Parameter(Mandatory = $true)]
        [string] $RunId,
        [int] $TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $run = Invoke-Utf8Json `
            -Uri "$BaseUrl/v1/runs/$RunId" `
            -Headers $Headers
        if ($run.status -in @("completed", "failed", "cancelled", "interrupted")) {
            return $run
        }
        Start-Sleep -Milliseconds 200
    }
    throw "Run $RunId did not reach a terminal state within $TimeoutSeconds seconds."
}

function Get-RunEvents {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BaseUrl,
        [Parameter(Mandatory = $true)]
        [string] $Token,
        [Parameter(Mandatory = $true)]
        [string] $RunId
    )

    $eventText = & curl.exe `
        --silent `
        --show-error `
        --fail `
        --max-time 15 `
        -H "Authorization: Bearer $Token" `
        "$BaseUrl/v1/runs/$RunId/events"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read events for run $RunId."
    }
    $eventText = $eventText -join "`n"
    return @(
        $eventText -split "`n" |
            Where-Object { $_ -like "data: *" } |
            ForEach-Object { ($_ -replace "^data: ", "") | ConvertFrom-Json }
    )
}

function New-Spec {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BaseUrl,
        [Parameter(Mandatory = $true)]
        [hashtable] $Headers,
        [Parameter(Mandatory = $true)]
        [hashtable] $Payload
    )

    return Invoke-Utf8Json `
        -Uri "$BaseUrl/v1/specs" `
        -Method Post `
        -Headers $Headers `
        -ContentType "application/json; charset=utf-8" `
        -Body ($Payload | ConvertTo-Json -Depth 20 -Compress)
}

function Start-AgentRun {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BaseUrl,
        [Parameter(Mandatory = $true)]
        [hashtable] $Headers,
        [Parameter(Mandatory = $true)]
        [object] $Spec,
        [Parameter(Mandatory = $true)]
        [string] $InputText
    )

    $body = @{
        spec_id = $Spec.agent_id
        version = $Spec.spec.version
        input = $InputText
    } | ConvertTo-Json -Compress
    return Invoke-Utf8Json `
        -Uri "$BaseUrl/v1/runs" `
        -Method Post `
        -Headers $Headers `
        -ContentType "application/json; charset=utf-8" `
        -Body $body
}

function Assert-EventSequence {
    param(
        [Parameter(Mandatory = $true)]
        [object[]] $Events,
        [Parameter(Mandatory = $true)]
        [string[]] $Expected,
        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    $actual = @($Events | ForEach-Object { $_.type })
    if (($actual -join ",") -ne ($Expected -join ",")) {
        throw "$Label events differ. Expected $($Expected -join ','); got $($actual -join ',')."
    }
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process] $Process)

    if ($null -eq $Process) {
        return
    }
    $processId = $Process.Id
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        Stop-Process -Id $processId -Force
        Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path -LiteralPath $binaryPath)) {
    throw "Packaged sidecar is missing. Run npm run sidecar:build first."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment is missing. Run uv sync first."
}
if (-not (Test-Path -LiteralPath $mockProviderScript)) {
    throw "Mock provider script is missing."
}
if (-not (Test-Path -LiteralPath $mcpFixture)) {
    throw "MCP fixture is missing."
}

New-Item -ItemType Directory -Force -Path $smokeRoot, $runtimeTemp | Out-Null
$artifacts = @(
    $databasePath,
    "$databasePath-wal",
    "$databasePath-shm",
    (Join-Path $smokeRoot "mock.stdout.log"),
    (Join-Path $smokeRoot "mock.stderr.log"),
    (Join-Path $smokeRoot "sidecar-1.stdout.log"),
    (Join-Path $smokeRoot "sidecar-1.stderr.log"),
    (Join-Path $smokeRoot "sidecar-2.stdout.log"),
    (Join-Path $smokeRoot "sidecar-2.stderr.log")
)
foreach ($artifact in $artifacts) {
    Remove-Item -LiteralPath $artifact -Force -ErrorAction SilentlyContinue
}

$launchToken = New-RandomHex
$providerKey = New-RandomHex
$packageSha256 = Get-Sha256 -LiteralPath $binaryPath
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$env:TEMP = $runtimeTemp
$env:TMP = $runtimeTemp

$mockProcess = $null
$sidecarProcess = $null
$knowledgeTerm = -join ([char[]](0x53D1, 0x5E03, 0x4F1A, 0x8BDD))
$knowledgeAnswerPrefix = -join ([char[]](0x77E5, 0x8BC6, 0x5E93, 0x56DE, 0x7B54))

try {
    $env:AGENT_CROSSBAR_TEST_PROVIDER_KEY = $providerKey
    $env:AGENT_CROSSBAR_TEST_MCP_TOOL = "1"
    $env:AGENT_CROSSBAR_TEST_KNOWLEDGE = "1"

    $mock = Start-MockProvider `
        -StdoutPath (Join-Path $smokeRoot "mock.stdout.log") `
        -StderrPath (Join-Path $smokeRoot "mock.stderr.log")
    $mockProcess = $mock.Process

    $env:AGENT_CROSSBAR_OPENAI_BASE_URL = "http://127.0.0.1:$($mock.Port)/v1"
    $env:AGENT_CROSSBAR_OPENAI_API_KEY = $providerKey
    $env:AGENT_CROSSBAR_OPENAI_MODEL = "mock-model"

    $sidecar = Start-Sidecar `
        -Token $launchToken `
        -StdoutPath (Join-Path $smokeRoot "sidecar-1.stdout.log") `
        -StderrPath (Join-Path $smokeRoot "sidecar-1.stderr.log")
    $sidecarProcess = $sidecar.Process
    $baseUrl = $sidecar.BaseUrl
    $headers = @{ Authorization = "Bearer $launchToken" }

    $unauthorizedStatus = $null
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/health" | Out-Null
        $unauthorizedStatus = 200
    } catch {
        $unauthorizedStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($unauthorizedStatus -ne 401) {
        throw "Unauthenticated health request returned $unauthorizedStatus instead of 401."
    }

    $health = Invoke-Utf8Json -Uri "$baseUrl/health" -Headers $headers
    if ($health.status -ne "ok" -or $health.database -ne "ready") {
        throw "The packaged sidecar health check did not report a ready database."
    }

    $knowledgeBody = @{
        title = "Release knowledge"
        source_name = "release-runbook.md"
        content = (
            "Before the $knowledgeTerm, verify authentication, persistence, and recovery. " +
            "The $knowledgeTerm must cite the runbook evidence."
        )
    } | ConvertTo-Json -Compress
    $knowledgeDocument = Invoke-Utf8Json `
        -Uri "$baseUrl/v1/knowledge/documents" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json; charset=utf-8" `
        -Body $knowledgeBody
    $knowledgeSearch = Invoke-Utf8Json `
        -Uri "$baseUrl/v1/knowledge/search?q=$([uri]::EscapeDataString($knowledgeTerm))&limit=3" `
        -Headers $headers
    if ($knowledgeSearch.results.Count -lt 1) {
        throw "The packaged knowledge search returned no results."
    }
    $knowledgeHit = $knowledgeSearch.results[0]
    $knowledgeHitIsInvalid = (
        $knowledgeHit.document_id -ne $knowledgeDocument.document_id -or
        $knowledgeHit.rank -ne 0 -or
        $knowledgeHit.source_name -ne "release-runbook.md" -or
        $knowledgeHit.content -notlike "*$knowledgeTerm*" -or
        $knowledgeHit.excerpt -notlike "*$knowledgeTerm*"
    )
    if ($knowledgeHitIsInvalid) {
        $knowledgeDiagnostics = $knowledgeSearch | ConvertTo-Json -Depth 8 -Compress
        throw "The packaged knowledge search did not return ranked evidence with a citation. Response: $knowledgeDiagnostics"
    }
    if ($knowledgeHit.score -isnot [double] -and $knowledgeHit.score -isnot [decimal]) {
        throw "The packaged knowledge result did not expose a numeric BM25 score."
    }

    $mcpBody = @{
        label = "Packaged echo MCP"
        transport = "stdio"
        command = $python
        args = @($mcpFixture)
        env_keys = @()
        enabled = $true
    } | ConvertTo-Json -Depth 10 -Compress
    $mcpServer = Invoke-Utf8Json `
        -Uri "$baseUrl/v1/mcp/servers" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json; charset=utf-8" `
        -Body $mcpBody
    $mcpServer = Invoke-Utf8Json `
        -Uri "$baseUrl/v1/mcp/servers/$($mcpServer.server_id)/discover" `
        -Method Post `
        -Headers $headers
    $echoTool = @($mcpServer.tools | Where-Object { $_.tool_name -eq "echo" }) | Select-Object -First 1
    if ($null -eq $echoTool) {
        throw "The packaged MCP discovery did not return the echo tool."
    }

    $ragSpec = New-Spec -BaseUrl $baseUrl -Headers $headers -Payload @{
        name = "RAG release agent"
        version = "1.0.0"
        description = "Packaged RAG integration proof"
        model_profile = "openai.default"
        instructions = "Use knowledge_search and cite the returned evidence."
        tools = @(
            @{
                name = "knowledge_search"
                description = "Search the local release knowledge base."
            }
        )
    }
    $ragRun = Start-AgentRun `
        -BaseUrl $baseUrl `
        -Headers $headers `
        -Spec $ragSpec `
        -InputText "Answer from the release knowledge base."
    $ragTerminal = Wait-Run `
        -BaseUrl $baseUrl `
        -Headers $headers `
        -RunId $ragRun.run_id
    $ragEvents = Get-RunEvents `
        -BaseUrl $baseUrl `
        -Token $launchToken `
        -RunId $ragRun.run_id
    Assert-EventSequence `
        -Events @($ragEvents | Where-Object { $_.type -in @(
            "tool_proposed",
            "tool_started",
            "tool_completed",
            "run_completed"
        ) }) `
        -Expected @("tool_proposed", "tool_started", "tool_completed", "run_completed") `
        -Label "RAG"
    $ragRunIsInvalid = (
        $ragTerminal.status -ne "completed" -or
        $ragTerminal.output -notlike "*$knowledgeAnswerPrefix*" -or
        $ragTerminal.output -notlike "*$knowledgeTerm*"
    )
    if ($ragRunIsInvalid) {
        throw "The packaged RAG run did not complete with retrieved knowledge evidence."
    }
    $knowledgeToolResult = @(
        $ragEvents |
            Where-Object { $_.type -eq "tool_completed" }
    )[0].payload.content
    if ($knowledgeToolResult -notlike "*$knowledgeTerm*") {
        throw "The packaged knowledge_search tool did not return persisted content."
    }

    $mcpSpec = New-Spec -BaseUrl $baseUrl -Headers $headers -Payload @{
        name = "MCP release agent"
        version = "1.0.0"
        description = "Packaged MCP integration proof"
        model_profile = "openai.default"
        instructions = "Call the discovered MCP tool."
        tools = @(
            @{
                name = $echoTool.exposed_name
                description = "Call the discovered echo tool."
            }
        )
    }
    $mcpRun = Start-AgentRun `
        -BaseUrl $baseUrl `
        -Headers $headers `
        -Spec $mcpSpec `
        -InputText "Invoke the MCP echo tool."
    $mcpTerminal = Wait-Run -BaseUrl $baseUrl -Headers $headers -RunId $mcpRun.run_id
    $mcpEvents = Get-RunEvents -BaseUrl $baseUrl -Token $launchToken -RunId $mcpRun.run_id
    Assert-EventSequence `
        -Events @($mcpEvents | Where-Object { $_.type -in @(
            "tool_proposed",
            "tool_started",
            "tool_completed",
            "run_completed"
        ) }) `
        -Expected @("tool_proposed", "tool_started", "tool_completed", "run_completed") `
        -Label "MCP"
    $mcpRunIsInvalid = (
        $mcpTerminal.status -ne "completed" -or
        $mcpTerminal.output -notlike "*MCP result:*" -or
        $mcpTerminal.output -notlike "*echo:*"
    )
    if ($mcpRunIsInvalid) {
        throw "The packaged MCP run did not complete with the echoed tool result."
    }

    $langGraphSpec = New-Spec -BaseUrl $baseUrl -Headers $headers -Payload @{
        name = "LangGraph release agent"
        version = "1.0.0"
        runtime = "langgraph"
        model_profile = "local.tool-demo"
        instructions = "Use the calculator when arithmetic is required."
        tools = @(
            @{
                name = "calculator"
                description = "Evaluate a safe arithmetic expression."
            }
        )
    }
    $langGraphRun = Start-AgentRun `
        -BaseUrl $baseUrl `
        -Headers $headers `
        -Spec $langGraphSpec `
        -InputText "Calculate two plus two."
    $langGraphTerminal = Wait-Run `
        -BaseUrl $baseUrl `
        -Headers $headers `
        -RunId $langGraphRun.run_id
    $langGraphEvents = Get-RunEvents `
        -BaseUrl $baseUrl `
        -Token $launchToken `
        -RunId $langGraphRun.run_id
    Assert-EventSequence `
        -Events $langGraphEvents `
        -Expected @(
            "run_started",
            "model_started",
            "model_completed",
            "tool_proposed",
            "tool_started",
            "tool_completed",
            "model_started",
            "model_completed",
            "text_delta",
            "run_completed"
        ) `
        -Label "LangGraph"
    $langGraphRunIsInvalid = (
        $langGraphTerminal.status -ne "completed" -or
        $langGraphTerminal.output -ne "The answer is 4." -or
        $langGraphEvents[0].payload.runtime -ne "langgraph" -or
        $langGraphEvents[0].payload.framework -ne "langgraph.StateGraph"
    )
    if ($langGraphRunIsInvalid) {
        throw "The packaged LangGraph adapter did not execute its tool conditional graph."
    }

    $childSpec = New-Spec -BaseUrl $baseUrl -Headers $headers -Payload @{
        name = "Delegated evidence agent"
        version = "1.0.0"
        description = "Authorized child agent"
        runtime = "native"
        model_profile = "local.echo"
        instructions = "Respond with the delegated evidence."
    }
    $parentSpec = New-Spec -BaseUrl $baseUrl -Headers $headers -Payload @{
        name = "Supervisor release agent"
        version = "1.0.0"
        description = "Packaged multi-agent integration proof"
        runtime = "native"
        model_profile = "local.delegate-demo"
        instructions = "Delegate to the authorized evidence agent."
        collaboration = @{
            mode = "supervisor"
            max_agents = 2
            members = @(
                @{
                    agent_id = $childSpec.agent_id
                    version = $childSpec.spec.version
                    role = "Review delegated evidence"
                }
            )
        }
    }
    $parentRun = Start-AgentRun `
        -BaseUrl $baseUrl `
        -Headers $headers `
        -Spec $parentSpec `
        -InputText "Coordinate the release review."
    $parentTerminal = Wait-Run `
        -BaseUrl $baseUrl `
        -Headers $headers `
        -RunId $parentRun.run_id
    $parentEvents = Get-RunEvents `
        -BaseUrl $baseUrl `
        -Token $launchToken `
        -RunId $parentRun.run_id
    $handoffStarted = @($parentEvents | Where-Object { $_.type -eq "handoff_started" })
    $handoffCompleted = @($parentEvents | Where-Object { $_.type -eq "handoff_completed" })
    $delegationRunIsInvalid = (
        $parentTerminal.status -ne "completed" -or
        $parentTerminal.output -notlike "Delegated result received:*" -or
        $handoffStarted.Count -ne 1 -or
        $handoffCompleted.Count -ne 1
    )
    if ($delegationRunIsInvalid) {
        throw "The packaged delegation did not emit a complete handoff lifecycle."
    }
    $childRunId = $handoffCompleted[0].payload.child_run_id
    $runTree = Invoke-Utf8Json `
        -Uri "$baseUrl/v1/runs/$($parentRun.run_id)/tree" `
        -Headers $headers
    if ($runTree.children.Count -ne 1) {
        throw "The packaged run tree did not contain exactly one delegated child."
    }
    $childNode = $runTree.children[0]
    $childNodeIsInvalid = (
        $childNode.run.run_id -ne $childRunId -or
        $childNode.run.parent_run_id -ne $parentRun.run_id -or
        $childNode.run.root_run_id -ne $parentRun.run_id -or
        $childNode.run.delegation_depth -ne 1 -or
        $childNode.run.status -ne "completed"
    )
    if ($childNodeIsInvalid) {
        throw "The packaged delegated child run has an invalid tree relationship."
    }

    $journalMode = & $python -c `
        "import sqlite3, sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('PRAGMA journal_mode').fetchone()[0]); c.close()" `
        $databasePath
    if ($LASTEXITCODE -ne 0 -or $journalMode.Trim().ToLowerInvariant() -ne "wal") {
        throw "The packaged SQLite database is not using WAL mode."
    }

    $specCountBeforeRestart = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/specs" -Headers $headers
    ).Count
    $documentCountBeforeRestart = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/knowledge/documents" -Headers $headers
    ).Count
    $mcpCountBeforeRestart = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/mcp/servers" -Headers $headers
    ).Count
    $runIdsBeforeRestart = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/runs" -Headers $headers |
            ForEach-Object { $_.run_id }
    )
    $ragEventCountBeforeRestart = $ragEvents.Count

    Stop-ProcessTree -Process $sidecarProcess
    $sidecarProcess = $null
    Start-Sleep -Seconds 2

    $restarted = Start-Sidecar `
        -Token $launchToken `
        -StdoutPath (Join-Path $smokeRoot "sidecar-2.stdout.log") `
        -StderrPath (Join-Path $smokeRoot "sidecar-2.stderr.log")
    $sidecarProcess = $restarted.Process
    $baseUrl = $restarted.BaseUrl

    $persistedSpecs = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/specs" -Headers $headers
    )
    $persistedDocuments = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/knowledge/documents" -Headers $headers
    )
    $persistedMcp = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/mcp/servers" -Headers $headers
    )
    $persistedRuns = @(
        Invoke-Utf8Json -Uri "$baseUrl/v1/runs" -Headers $headers
    )
    $persistedTree = Invoke-Utf8Json `
        -Uri "$baseUrl/v1/runs/$($parentRun.run_id)/tree" `
        -Headers $headers
    $persistedRagEvents = Get-RunEvents `
        -BaseUrl $baseUrl `
        -Token $launchToken `
        -RunId $ragRun.run_id

    $restartPersistenceIsInvalid = (
        $persistedSpecs.Count -ne $specCountBeforeRestart -or
        $persistedDocuments.Count -ne $documentCountBeforeRestart -or
        $persistedMcp.Count -ne $mcpCountBeforeRestart -or
        $persistedRuns.Count -ne $runIdsBeforeRestart.Count -or
        $persistedRagEvents.Count -ne $ragEventCountBeforeRestart -or
        $persistedTree.children[0].run.run_id -ne $childRunId
    )
    if ($restartPersistenceIsInvalid) {
        $persistenceDiagnostics = [pscustomobject]@{
            specs = @($specCountBeforeRestart, $persistedSpecs.Count)
            documents = @($documentCountBeforeRestart, $persistedDocuments.Count)
            mcpServers = @($mcpCountBeforeRestart, $persistedMcp.Count)
            runs = @($runIdsBeforeRestart.Count, $persistedRuns.Count)
            ragEvents = @($ragEventCountBeforeRestart, $persistedRagEvents.Count)
            childRunId = @($childRunId, $persistedTree.children[0].run.run_id)
        } | ConvertTo-Json -Depth 6 -Compress
        throw "Restarted sidecar did not preserve all persisted control-plane evidence. State: $persistenceDiagnostics"
    }
    foreach ($previousRunId in $runIdsBeforeRestart) {
        if ($previousRunId -notin @($persistedRuns | ForEach-Object { $_.run_id })) {
            throw "Run $previousRunId was not preserved after the sidecar restart."
        }
    }

    [pscustomobject]@{
        status = "passed"
        targetTriple = $targetTriple
        sidecarSha256 = $packageSha256
        database = $databasePath
        journalMode = $journalMode.Trim().ToLowerInvariant()
        auth = [pscustomobject]@{
            unauthorizedStatus = $unauthorizedStatus
            authorizedHealth = $health.status
        }
        rag = [pscustomobject]@{
            documentId = $knowledgeDocument.document_id
            rank = $knowledgeHit.rank
            score = $knowledgeHit.score
            output = $ragTerminal.output
            eventCount = $ragEvents.Count
        }
        mcp = [pscustomobject]@{
            serverId = $mcpServer.server_id
            tool = $echoTool.exposed_name
            output = $mcpTerminal.output
        }
        langGraph = [pscustomobject]@{
            runtime = $langGraphEvents[0].payload.runtime
            framework = $langGraphEvents[0].payload.framework
            output = $langGraphTerminal.output
            eventTypes = @($langGraphEvents | ForEach-Object { $_.type })
        }
        delegation = [pscustomobject]@{
            parentRunId = $parentRun.run_id
            childRunId = $childRunId
            parentRootRunId = $parentTerminal.root_run_id
            childParentRunId = $childNode.run.parent_run_id
            childRootRunId = $childNode.run.root_run_id
            delegationDepth = $childNode.run.delegation_depth
            handoffStarted = $handoffStarted.Count
            handoffCompleted = $handoffCompleted.Count
            output = $parentTerminal.output
        }
        restart = [pscustomobject]@{
            specs = $persistedSpecs.Count
            documents = $persistedDocuments.Count
            mcpServers = $persistedMcp.Count
            runs = $persistedRuns.Count
            ragEvents = $persistedRagEvents.Count
            runTreePreserved = $true
        }
    } | ConvertTo-Json -Depth 10
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    Stop-ProcessTree -Process $sidecarProcess
    Stop-ProcessTree -Process $mockProcess
}
