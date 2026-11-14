"""Run the reproducible Agent Crossbar retrieval benchmark.

The benchmark ingests the checked-in synthetic corpus through the public API,
verifies that every document becomes exactly one chunk, and measures lexical,
vector, and hybrid retrieval against document/chunk-level ground truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from agent_crossbar.api.app import AppSettings, create_app
from fastapi.testclient import TestClient

_TOKEN = "rag-benchmark-launch-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_MODES = ("lexical", "vector", "hybrid")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    ranks = [row["rank"] for row in rows]
    latencies = [row["latency_ms"] for row in rows]
    return {
        "queries": count,
        "r_at_1": round(sum(1 for rank in ranks if rank == 1) / count, 4),
        "r_at_3": round(sum(1 for rank in ranks if 0 < rank <= 3) / count, 4),
        "r_at_5": round(sum(1 for rank in ranks if 0 < rank <= 5) / count, 4),
        "mrr": round(
            sum(1.0 / rank if rank > 0 else 0.0 for rank in ranks) / count,
            4,
        ),
        "p50_latency_ms": round(statistics.median(latencies), 3),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 3),
    }


def _markdown(report: dict[str, Any]) -> str:
    hybrid_semantic_r1 = report["modes"]["hybrid"]["by_kind"]["semantic"]["r_at_1"]
    vector_semantic_r1 = report["modes"]["vector"]["by_kind"]["semantic"]["r_at_1"]
    lines = [
        "# Agent Crossbar RAG Benchmark",
        "",
        f"**Generated:** {report['generated_at']}",
        "",
        "**Corpus:** checked-in synthetic corpus, no external or private documents",
        "",
        f"**Corpus SHA-256:** `{report['corpus_sha256']}`",
        "",
        f"**Embedding model:** `{report['embedding']['model']}` "
        f"({report['embedding']['dimensions']} dimensions, local HTTP endpoint)",
        "",
        f"**Documents / chunks / queries:** {report['documents']} / "
        f"{report['chunks']} / {report['queries']}",
        "",
        "## Overall results",
        "",
        "| Mode | R@1 | R@3 | R@5 | MRR | P50 ms | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in _MODES:
        item = report["modes"][mode]
        lines.append(
            f"| {mode} | {item['r_at_1']:.4f} | {item['r_at_3']:.4f} | "
            f"{item['r_at_5']:.4f} | {item['mrr']:.4f} | "
            f"{item['p50_latency_ms']:.3f} | {item['p95_latency_ms']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Results by query type",
            "",
            "| Mode | Query type | Queries | R@1 | R@5 | MRR |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for mode in _MODES:
        for kind in ("lexical", "semantic", "mixed"):
            item = report["modes"][mode]["by_kind"][kind]
            lines.append(
                f"| {mode} | {kind} | {item['queries']} | {item['r_at_1']:.4f} | "
                f"{item['r_at_5']:.4f} | {item['mrr']:.4f} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation and limits",
            "",
            f"- Hybrid has the best R@5 ({report['modes']['hybrid']['r_at_5']:.4f}), "
            "while vector has the best R@1. RRF improves tail recall here, not top-1 "
            "precision.",
            f"- Hybrid semantic R@1 is {hybrid_semantic_r1:.4f}, "
            f"below vector semantic R@1 ({vector_semantic_r1:.4f}). "
            "The lexical channel can add noise on paraphrased questions; this is a real "
            "limitation, not a benchmark artifact to hide.",
            "- The corpus is synthetic, one chunk per document, and only 24 documents. "
            "It does not measure long-document chunk boundaries, OCR, permission-aware "
            "retrieval, or production traffic.",
            "- Latency is local single-process latency. It is not an ANN-scale result; "
            "the current vector path scans stored vectors in Python.",
            "",
            "## Method",
            "",
            "- Every query is sent through `GET /v1/knowledge/search` with `limit=5`.",
            "- Ground truth is the expected document's first chunk; ingestion asserts "
            "exactly one chunk per document.",
            "- Rank 0 means the expected chunk was absent from the top five.",
            "- MRR counts a miss as zero. Latency includes the local HTTP API boundary "
            "and vector scoring, not model loading.",
            "- `lexical` forces FTS5 BM25 plus substring fallback; `vector` forces "
            "cosine similarity; `hybrid` uses RRF over both channels.",
            "",
            "## Reproduction",
            "",
            "```powershell",
            "python scripts/local-embedding-server.py --model BAAI/bge-small-zh-v1.5 --port 18888",
            "python scripts/rag-benchmark.py --embedding-url http://127.0.0.1:18888/v1 `",
            "  --output docs/verification/rag-benchmark.md `",
            "  --json-output docs/verification/rag-benchmark.json",
            "```",
            "",
            "The repository ships a synthetic corpus and ground-truth queries, so the "
            "benchmark can be rerun after cloning. The embedding model is an external "
            "prerequisite and is not vendored.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="scripts/rag_benchmark/corpus.json")
    parser.add_argument("--embedding-url", default="http://127.0.0.1:18888/v1")
    parser.add_argument("--embedding-model", default="bge-small-zh-v1.5")
    parser.add_argument("--output", default="docs/verification/rag-benchmark.md")
    parser.add_argument("--json-output", default="docs/verification/rag-benchmark.json")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    documents = payload["documents"]
    queries = payload["queries"]

    health_url = args.embedding_url.rstrip("/").removesuffix("/v1") + "/health"
    health = httpx.get(health_url, timeout=10.0)
    health.raise_for_status()
    health_payload = health.json()

    with tempfile.TemporaryDirectory(prefix="crossbar-rag-benchmark-") as directory:
        settings = AppSettings(
            database_path=Path(directory) / "benchmark.db",
            launch_token=_TOKEN,
        )
        app = create_app(settings)
        with TestClient(app) as client:
            response = client.put(
                "/v1/knowledge/embedding/configuration",
                headers=_AUTH,
                json={
                    "base_url": args.embedding_url,
                    "api_key": "local-benchmark-key",
                    "model": args.embedding_model,
                },
            )
            response.raise_for_status()

            expected_chunks: dict[str, str] = {}
            for document in documents:
                created = client.post(
                    "/v1/knowledge/documents",
                    headers=_AUTH,
                    json={
                        "title": document["title"],
                        "source_name": document["slug"],
                        "content": document["content"],
                    },
                )
                created.raise_for_status()
                record = created.json()
                if record["chunk_count"] != 1:
                    raise RuntimeError(
                        f"document {document['slug']} produced {record['chunk_count']} chunks; "
                        "the benchmark currently requires one chunk per document"
                    )
                row = app.state.database.connection.execute(
                    "SELECT chunk_id FROM knowledge_chunks WHERE document_id = ?",
                    (record["document_id"],),
                ).fetchone()
                expected_chunks[document["slug"]] = str(row["chunk_id"])

            index_status = client.get("/v1/knowledge/index", headers=_AUTH).json()
            if index_status["state"] != "ready":
                raise RuntimeError(f"embedding index is not ready: {index_status}")

            rows: dict[str, list[dict[str, Any]]] = {mode: [] for mode in _MODES}
            for mode in _MODES:
                for item in queries:
                    expected_chunk = expected_chunks[item["expected"]]
                    started = time.perf_counter()
                    searched = client.get(
                        "/v1/knowledge/search",
                        headers=_AUTH,
                        params={"q": item["query"], "limit": 5, "mode": mode},
                    )
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    searched.raise_for_status()
                    result = searched.json()
                    hit_ids = [hit["chunk_id"] for hit in result["results"]]
                    rank = (
                        hit_ids.index(expected_chunk) + 1
                        if expected_chunk in hit_ids
                        else 0
                    )
                    rows[mode].append(
                        {
                            "query": item["query"],
                            "kind": item["kind"],
                            "expected": item["expected"],
                            "rank": rank,
                            "latency_ms": round(elapsed_ms, 3),
                            "retrieval_mode": result["mode"],
                            "degraded_reason": result["degraded_reason"],
                        }
                    )

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "corpus_sha256": _sha256(corpus_path),
        "embedding": {
            "model": health_payload["model"],
            "dimensions": health_payload["dimensions"],
            "endpoint": args.embedding_url,
        },
        "documents": len(documents),
        "chunks": len(expected_chunks),
        "queries": len(queries),
        "modes": {},
        "rows": rows,
    }
    for mode in _MODES:
        mode_rows = rows[mode]
        report["modes"][mode] = {
            **_metrics(mode_rows),
            "by_kind": {
                kind: _metrics([row for row in mode_rows if row["kind"] == kind])
                for kind in ("lexical", "semantic", "mixed")
            },
            "misses": [row for row in mode_rows if row["rank"] == 0][:10],
        }

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    markdown_path = Path(args.output)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(report), encoding="utf-8")

    for mode in _MODES:
        item = report["modes"][mode]
        print(
            f"{mode}: R@1={item['r_at_1']:.4f} R@5={item['r_at_5']:.4f} "
            f"MRR={item['mrr']:.4f} P95={item['p95_latency_ms']:.3f}ms"
        )


if __name__ == "__main__":
    main()
