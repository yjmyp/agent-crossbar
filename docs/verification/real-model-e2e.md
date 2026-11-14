# Real External Model End-to-End Evidence

**Generated:** 2026-11-13T19:11:16.187483+00:00

**Provider:** `https://api.deepseek.com`

**Requested model:** `deepseek-chat`

**Provider-reported model:** `deepseek-flash`

**Run ID:** `run_38ef90a72c644f45a2baa949861ff7c2`

**Status:** completed

**Knowledge retrieval mode:** `hybrid`

**Retrieval degraded reason:** `None`

## Evidence

- A direct request to the same external endpoint returned successfully before the runtime call.
- The run used the `openai.default` profile and the native runtime.
- The model called `knowledge_search`; the tool result and final answer are in the normalized trace.
- Token counts below came from the external provider's usage object.
- The script searched the SQLite file for the exact API key and confirmed it was absent.

## Result

**Answer:** ORBITAL-47 的心跳窗口是 17 分钟。

| Metric | Value |
| --- | ---: |
| Model turns | 2 |
| Tool calls | 1 |
| Input tokens | 1051 |
| Output tokens | 63 |
| Total tokens | 1114 |
| Duration | 3062 ms |
| API key in SQLite | False |

## Tool trace

| Sequence | Event | Tool | Payload excerpt |
| ---: | --- | --- | --- |
| 4 | tool_proposed | knowledge_search | {"arguments": {"query": "ORBITAL-47 的心跳窗口是多少分钟？"}, "call_id": "call_00_1MyGysFu0pDM5PeE2PGZ5926", "name": "knowledge_search"} |
| 5 | tool_started | knowledge_search | {"call_id": "call_00_1MyGysFu0pDM5PeE2PGZ5926", "name": "knowledge_search"} |
| 6 | tool_completed | knowledge_search | {"call_id": "call_00_1MyGysFu0pDM5PeE2PGZ5926", "content": "{\"degraded_reason\":null,\"mode\":\"hybrid\",\"ok\":true,\"query\":\"ORBITAL-47 的心跳窗口是多少分钟？\",\"results\":[{\"chunk_id\":\"chk_b70d60df44785aae3f21310f\",\"content\":\"PROJECT ... |

## Reproduction

```powershell
$env:DEEPSEEK_API_KEY = '<your-key>'
python scripts/local-embedding-server.py --model BAAI/bge-small-zh-v1.5 --port 18888
python scripts/real-model-e2e.py `
  --base-url https://api.deepseek.com --model deepseek-chat `
  --embedding-url http://127.0.0.1:18888/v1
```

The script refuses to run without an API key and never writes the key to the report, database, trace, or command line.
