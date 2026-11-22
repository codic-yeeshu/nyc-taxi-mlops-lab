# 016: Wiki vector index

Stage: S6 · Date: 2026-11-22 · Author: YEESHU · Drafted by agent: yes

## Choice

Use HNSW with pgvector's cosine-distance operator class for wiki chunk retrieval.

## Rejected alternative

Use IVFFlat and tune the number of lists and probes after loading a representative corpus.

## Why

The lab starts with a small wiki that changes daily. HNSW can build before enough data exists to train list centroids and can accept newly embedded chunks as they arrive. Its build time and memory cost are a trade-off for the typical speed–recall advantage. Postgres may still prefer an exact scan while the table is small.

## What would show this was wrong

At one million chunks, benchmark recall@k against exact cosine search alongside query latency, index size, and update cost. Keep HNSW if it fits the RDS resource limits and meets the measured recall and latency needs. Compare tuned IVFFlat if HNSW exceeds the memory budget or builds and updates too slowly.
