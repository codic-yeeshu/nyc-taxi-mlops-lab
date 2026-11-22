"""S6: the wiki RAG branch, in the `rag` database on RDS (pgvector), on a daily schedule.

- wiki_pages: the published pages from the ops wiki (resource `wiki`: labpipes/wiki.py). Store each
  page's ETag and send it next time: an unchanged page then costs a 304 and no body.
- wiki_chunks: split changed pages with labpipes.chunking.chunk_markdown (chunk size and overlap are
  decision 015) and store the chunks; use Chunk.content_hash as the id so unchanged text keeps it.
- wiki_embeddings: embed only the chunks that have no vector yet (resource `embed`: nomic-embed-text,
  768 dimensions) and store them as pgvector `vector(768)`, with an index (HNSW or IVFFlat: decision 016).
- A blocking check that every chunk has a vector, and a schedule (and a job you can run by hand with
  scripts/dagster-run.sh) for the three.
The RDS admin connection comes from the `rag` resource (RagStore.connect); `create extension vector`
works there. Copy asset and check shapes from pipelines/reference/patterns.py.
"""

from contextlib import closing
import json
import math

import dagster as dg
from pydantic import Field

from ..chunking import chunk_markdown
from ..resources import LlmEmbed, RagStore, WikiApi

RAG_LOCK = 608601


@dg.asset(group_name="rag", kinds={"postgres"})
def wiki_pages(wiki: WikiApi, rag: RagStore) -> dg.MaterializeResult:
    """Sync the published page list and fetch bodies using the last successful ETags."""
    client = wiki.client()
    with closing(rag.connect()) as conn, conn, conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (RAG_LOCK,))
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("CREATE SCHEMA IF NOT EXISTS rag")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag.pages (
                id text PRIMARY KEY,
                title text NOT NULL,
                updated_at text NOT NULL,
                etag text NOT NULL,
                body text NOT NULL,
                chunked_etag text,
                chunk_max_tokens integer,
                chunk_overlap_tokens integer
            )
            """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag.chunks (
                id text PRIMARY KEY,
                page_id text NOT NULL REFERENCES rag.pages(id) ON DELETE CASCADE,
                heading text NOT NULL,
                content text NOT NULL,
                tokens integer NOT NULL,
                embedding vector(768)
            )
            """)
        cursor.execute("CREATE INDEX IF NOT EXISTS chunks_page_id_idx ON rag.chunks (page_id)")
        cursor.execute("SELECT id, etag FROM rag.pages")
        etags = dict(cursor.fetchall())
        refs = client.pages()
        fetched = 0
        for ref in refs:
            page = client.page(ref.id, etags.get(ref.id))
            if page is None:
                continue
            if page.id != ref.id:
                raise ValueError(f"Wiki returned a different page ID for {ref.id}")
            cursor.execute("""
                INSERT INTO rag.pages (id, title, updated_at, etag, body)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, updated_at = EXCLUDED.updated_at,
                    etag = EXCLUDED.etag, body = EXCLUDED.body, chunked_etag = NULL
                """, (page.id, page.title, page.updated_at, page.etag, page.body))
            fetched += 1
        cursor.execute("DELETE FROM rag.pages WHERE NOT (id = ANY(%s::text[]))", ([ref.id for ref in refs],))
        removed = cursor.rowcount
    return dg.MaterializeResult(metadata={
        "published_pages": len(refs), "pages_fetched": fetched,
        "pages_unchanged": len(refs) - fetched, "pages_removed": removed,
    })


class WikiChunkConfig(dg.Config):
    max_tokens: int = Field(default=220, gt=0, lt=2048)
    overlap_tokens: int = Field(default=32, ge=0)


@dg.asset(deps=[wiki_pages], group_name="rag", kinds={"postgres"})
def wiki_chunks(config: WikiChunkConfig, rag: RagStore) -> dg.MaterializeResult:
    """Replace changed pages' chunks while preserving vectors for identical content."""
    if config.overlap_tokens >= config.max_tokens:
        raise ValueError("Chunk overlap must be smaller than the chunk size")
    page_count = inserted = removed = 0
    with closing(rag.connect()) as conn, conn, conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (RAG_LOCK,))
        cursor.execute("""
            SELECT id, title, body, etag FROM rag.pages
            WHERE chunked_etag IS DISTINCT FROM etag
                OR chunk_max_tokens IS DISTINCT FROM %s
                OR chunk_overlap_tokens IS DISTINCT FROM %s
            ORDER BY id
            """, (config.max_tokens, config.overlap_tokens))
        pages = cursor.fetchall()
        for page_id, title, body, etag in pages:
            chunks = {
                chunk.content_hash(page_id): chunk
                for chunk in chunk_markdown(title, body, config.max_tokens, config.overlap_tokens)
            }
            cursor.execute(
                "DELETE FROM rag.chunks WHERE page_id = %s AND NOT (id = ANY(%s::text[]))",
                (page_id, list(chunks)),
            )
            removed += cursor.rowcount
            cursor.executemany("""
                INSERT INTO rag.chunks (id, page_id, heading, content, tokens)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """, [(key, page_id, chunk.heading, chunk.text, chunk.tokens) for key, chunk in chunks.items()])
            if chunks:
                inserted += cursor.rowcount
            cursor.execute("""
                UPDATE rag.pages SET chunked_etag = %s, chunk_max_tokens = %s, chunk_overlap_tokens = %s
                WHERE id = %s
                """, (etag, config.max_tokens, config.overlap_tokens, page_id))
            page_count += 1
        cursor.execute("SELECT count(*) FROM rag.chunks")
        chunk_count, = cursor.fetchone()
    return dg.MaterializeResult(metadata={
        "pages_chunked": page_count, "chunks_inserted": inserted, "chunks_removed": removed,
        "chunks_total": chunk_count,
    })


@dg.asset(deps=[wiki_chunks], group_name="rag", kinds={"postgres"})
def wiki_embeddings(embed: LlmEmbed, rag: RagStore) -> dg.MaterializeResult:
    """Embed only chunks without vectors, in bounded batches."""
    with closing(rag.connect()) as conn, conn, conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (RAG_LOCK,))
        embedded = 0
        while True:
            cursor.execute("""
                SELECT c.id, c.content FROM rag.chunks AS c JOIN rag.pages AS p ON p.id = c.page_id
                WHERE c.embedding IS NULL AND p.chunked_etag = p.etag
                ORDER BY c.id LIMIT %s
                """, (embed.batch,))
            chunks = cursor.fetchall()
            if not chunks:
                break
            vectors = embed.embed_documents([content for _, content in chunks])
            updates = []
            for (chunk_id, _), vector in zip(chunks, vectors, strict=True):
                if len(vector) != 768 or not all(map(math.isfinite, vector)) or not any(vector):
                    raise ValueError(f"Invalid cosine embedding for chunk {chunk_id}")
                updates.append((json.dumps(vector), chunk_id))
            cursor.executemany("UPDATE rag.chunks SET embedding = %s::vector WHERE id = %s", updates)
            embedded += len(updates)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS chunks_embedding_cosine_idx
            ON rag.chunks USING hnsw (embedding vector_cosine_ops)
            """)
    return dg.MaterializeResult(metadata={"chunks_embedded": embedded})


@dg.asset_check(asset=wiki_embeddings, blocking=True, description="Every published page is chunked and every chunk has a vector.")
def embeddings_complete(rag: RagStore) -> dg.AssetCheckResult:
    with closing(rag.connect()) as conn, conn, conn.cursor() as cursor:
        cursor.execute("""
            SELECT (SELECT count(*) FROM rag.pages WHERE chunked_etag IS DISTINCT FROM etag),
                   (SELECT count(*) FROM rag.chunks WHERE embedding IS NULL)
            """)
        unchunked, missing = cursor.fetchone()
    return dg.AssetCheckResult(passed=(unchunked == missing == 0), metadata={
        "unchunked_pages": unchunked, "missing_embeddings": missing,
    })


ingest_wiki = dg.define_asset_job("ingest_wiki", selection=dg.AssetSelection.assets(wiki_pages, wiki_chunks, wiki_embeddings))

daily_wiki_ingest = dg.ScheduleDefinition(
    name="daily_wiki_ingest",
    job=ingest_wiki,
    cron_schedule="0 9 * * *",
    execution_timezone="Asia/Kolkata",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)
