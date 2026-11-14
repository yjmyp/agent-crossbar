"""Serve a local sentence-transformers model through an OpenAI-compatible API.

This is development and verification tooling, not a production embedding
service. Install the optional dependencies in an isolated environment:

    uv pip install sentence-transformers fastapi uvicorn

Then run:

    python scripts/local-embedding-server.py --model BAAI/bge-small-zh-v1.5 --port 8765
"""

from __future__ import annotations

import argparse
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer


class EmbeddingRequest(BaseModel):
    model: str = Field(min_length=1)
    input: str | list[str]


def create_app(model_name: str) -> FastAPI:
    model = SentenceTransformer(model_name)
    dimensions = int(model.get_sentence_embedding_dimension() or 0)
    app = FastAPI(title="Local OpenAI-compatible embedding server")

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "ok": True,
            "model": model_name,
            "dimensions": dimensions,
        }

    @app.post("/v1/embeddings")
    async def embeddings(payload: EmbeddingRequest) -> dict[str, Any]:
        texts = [payload.input] if isinstance(payload.input, str) else payload.input
        vectors = model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return {
            "object": "list",
            "model": payload.model,
            "data": [
                {
                    "object": "embedding",
                    "index": index,
                    "embedding": vector.tolist(),
                }
                for index, vector in enumerate(vectors)
            ],
            "usage": {
                "prompt_tokens": sum(len(text.split()) for text in texts),
                "total_tokens": sum(len(text.split()) for text in texts),
            },
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        create_app(args.model),
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
