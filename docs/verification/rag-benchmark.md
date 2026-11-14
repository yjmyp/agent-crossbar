# Agent Crossbar RAG Benchmark

**Generated:** 2026-11-13T19:20:14.548383+00:00

**Corpus:** checked-in synthetic corpus, no external or private documents

**Corpus SHA-256:** `3d2fd0dc66d4c4245c9f6d43ac15570c1597963947ad175bfbd08ae45f542d38`

**Embedding model:** `BAAI/bge-small-zh-v1.5` (512 dimensions, local HTTP endpoint)

**Documents / chunks / queries:** 24 / 24 / 72

## Overall results

| Mode | R@1 | R@3 | R@5 | MRR | P50 ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | 0.8472 | 0.8889 | 0.8889 | 0.8681 | 5.484 | 10.317 |
| vector | 0.8889 | 0.9583 | 0.9583 | 0.9236 | 59.431 | 78.600 |
| hybrid | 0.8750 | 0.9722 | 0.9722 | 0.9190 | 57.269 | 77.692 |

## Results by query type

| Mode | Query type | Queries | R@1 | R@5 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| lexical | lexical | 24 | 0.9583 | 1.0000 | 0.9792 |
| lexical | semantic | 24 | 0.5833 | 0.6667 | 0.6250 |
| lexical | mixed | 24 | 1.0000 | 1.0000 | 1.0000 |
| vector | lexical | 24 | 0.9167 | 1.0000 | 0.9583 |
| vector | semantic | 24 | 0.7500 | 0.8750 | 0.8125 |
| vector | mixed | 24 | 1.0000 | 1.0000 | 1.0000 |
| hybrid | lexical | 24 | 1.0000 | 1.0000 | 1.0000 |
| hybrid | semantic | 24 | 0.6250 | 0.9167 | 0.7569 |
| hybrid | mixed | 24 | 1.0000 | 1.0000 | 1.0000 |

## Interpretation and limits

- Hybrid has the best R@5 (0.9722), while vector has the best R@1. RRF improves tail recall here, not top-1 precision.
- Hybrid semantic R@1 is 0.6250, below vector semantic R@1 (0.7500). The lexical channel can add noise on paraphrased questions; this is a real limitation, not a benchmark artifact to hide.
- The corpus is synthetic, one chunk per document, and only 24 documents. It does not measure long-document chunk boundaries, OCR, permission-aware retrieval, or production traffic.
- Latency is local single-process latency. It is not an ANN-scale result; the current vector path scans stored vectors in Python.

## Method

- Every query is sent through `GET /v1/knowledge/search` with `limit=5`.
- Ground truth is the expected document's first chunk; ingestion asserts exactly one chunk per document.
- Rank 0 means the expected chunk was absent from the top five.
- MRR counts a miss as zero. Latency includes the local HTTP API boundary and vector scoring, not model loading.
- `lexical` forces FTS5 BM25 plus substring fallback; `vector` forces cosine similarity; `hybrid` uses RRF over both channels.

## Reproduction

```powershell
python scripts/local-embedding-server.py --model BAAI/bge-small-zh-v1.5 --port 18888
python scripts/rag-benchmark.py --embedding-url http://127.0.0.1:18888/v1 `
  --output docs/verification/rag-benchmark.md `
  --json-output docs/verification/rag-benchmark.json
```

The repository ships a synthetic corpus and ground-truth queries, so the benchmark can be rerun after cloning. The embedding model is an external prerequisite and is not vendored.
