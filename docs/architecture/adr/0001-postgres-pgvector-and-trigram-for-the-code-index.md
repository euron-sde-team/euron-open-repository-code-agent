# ADR 0001: Postgres with pgvector and pg_trgm holds the whole code index

## Status

Accepted.

## Context

CodeAgent needs four ways to find code: by symbol name (exact, prefix and fuzzy), by literal or regular expression across file contents, by meaning (vectors), and by walking the reference graph (callers and callees). Each is commonly served by a different system (a symbol database, a trigram or grep service, a vector database, a graph store). Running four stores multiplies operations and makes "one consistent snapshot of one commit" hard.

## Decision

Keep everything in PostgreSQL 16, in one transaction per snapshot:

- files, symbols, references and chunks are ordinary tables;
- `pg_trgm` GIN indexes serve text search (on file content) and fuzzy symbol names;
- `pgvector` with an HNSW index serves chunk embeddings, with iterative scanning so a snapshot filter still returns enough rows;
- a persisted `tsvector` column (the `simple` configuration over pre-split identifier terms) serves keyword ranking;
- the reference graph is a table queried by indexed foreign keys, and symbol detail needs one hop, not a graph traversal.

Semantic search fuses the vector and keyword lists with reciprocal rank fusion.

## Consequences

- One system to run, back up, secure and test, and one transaction makes a snapshot appear atomically.
- Content is stored in Postgres (up to `MAX_FILE_KB` per file), so the database grows with the code; it is bounded by `MAX_FILES` and `MAX_REPO_MB`, and old snapshots are pruned.
- Trigram search is slower than a dedicated code search engine on very large monorepos; the candidate narrowing and the statement timeout keep it safe, and the design leaves room to put a search engine behind the same repository methods.
- RDS must offer pgvector 0.8 and `pg_trgm`; both ship with PostgreSQL 16.5 and newer.

## Alternatives considered

A vector database plus a separate grep service (more moving parts, no shared snapshot); Elasticsearch or OpenSearch for text and vectors (a heavy dependency for what trigram indexes already do at this scale); a graph database for references (the queries are one or two hops)..
