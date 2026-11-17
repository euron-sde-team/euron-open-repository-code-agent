# ADR 0002: Every AI capability has a deterministic offline implementation, with models behind the same interface

## Status

Accepted.

## Context

Tests, demos and screenshots must work without an API key or a network, and reviewers must be able to trust a result they can reproduce. At the same time, some work (open-ended changes, fluent explanations) is only possible with a model, and teams will want to use their own.

## Decision

Each capability has an interface and at least one local implementation:

- **Embeddings:** `code-hash`, signed feature hashing of identifier sub-tokens, word pairs, character trigrams and a lexicon of programming concepts. Deterministic, 384 dimensions, no download. Adapters for OpenAI-compatible `/embeddings` and Ollama `/api/embed` sit behind the same interface, behind a read-through Valkey cache.
- **Answers:** an extractive answerer that composes cited sentences from facts the index holds (signatures, docstrings, callers, callees, tests). Adapters for OpenAI-compatible chat completions and Ollama `/api/chat`, both streamed.
- **Planner:** skills (rename through the reference graph, add a catalogued helper with tests, repair a failing test by verified mutation search). The model planner uses the same chat adapters with search-and-replace edit blocks and a test feedback loop.

A workspace can force the local engines (`agent_mode = local`). The engine in use is stored with every answer and patch and shown in the UI.

## Consequences

- The offline answerer cannot paraphrase or reason across many files; it states what the index shows and says so when it finds nothing. That is a feature for trust and a limit for fluency.
- The offline planner handles three kinds of task. Anything else fails with a message that lists them and how to configure a model, instead of guessing.
- Every capability has two implementations to keep correct; the interface is small and both are covered by tests.

## Alternatives considered

Requiring a model (no offline demo, unreproducible tests); shipping a small local model (a large download and slow CPU inference, and still not deterministic across platforms)..
