# Real External Model End-to-End Evidence

**Generated:** 2026-11-15T14:55:06.148261+00:00

**Provider:** `https://api.deepseek.com`

**Requested model:** `deepseek-v4-pro`

**Provider-reported model:** `deepseek-v4-pro`

**Run ID:** `run_441ebc15f0dd43c0a770e605d23fa3f0`

**Status:** completed

**Knowledge retrieval mode:** `lexical`

**Retrieval degraded reason:** `embedding_not_configured`

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
| Input tokens | 1267 |
| Output tokens | 123 |
| Total tokens | 1390 |
| Duration | 3137 ms |
| API key in SQLite | False |

## Tool trace

| Sequence | Event | Tool | Payload excerpt |
| ---: | --- | --- | --- |
| 4 | tool_proposed | knowledge_search | {"arguments": {"query": "ORBITAL-47 的心跳窗口是多少分钟"}, "call_id": "call_00_aJiXldKwIyU9KA1pQXCZ7913", "name": "knowledge_search"} |
| 5 | tool_started | knowledge_search | {"call_id": "call_00_aJiXldKwIyU9KA1pQXCZ7913", "name": "knowledge_search"} |
| 6 | tool_completed | knowledge_search | {"call_id": "call_00_aJiXldKwIyU9KA1pQXCZ7913", "content": "{\"degraded_reason\":\"embedding_not_configured\",\"mode\":\"lexical\",\"ok\":true,\"query\":\"ORBITAL-47 的心跳窗口是多少分钟\",\"results\":[{\"chunk_id\":\"chk_b70d60df44785aae3f21310f\... |

## Reproduction

```powershell
$env:DEEPSEEK_API_KEY = '<your-key>'
python scripts/real-model-e2e.py `
  --base-url https://api.deepseek.com --model deepseek-v4-pro
```

For hybrid retrieval, start `scripts/local-embedding-server.py` first and append `--embedding-url http://127.0.0.1:18888/v1`.

The script refuses to run without an API key and never writes the key to the report, database, trace, or command line.
