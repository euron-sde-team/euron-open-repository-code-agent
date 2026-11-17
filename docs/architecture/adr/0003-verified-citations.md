# ADR 0003: Citations are validated against the sources an answer was given

## Status

Accepted.

## Context

An answer that cites code is only useful if every citation opens real lines. Models invent source numbers, and a UI that renders them as links turns a hallucination into a dead end that looks like evidence.

## Decision

Sources are numbered when retrieval hands them to the answerer. After generation, `extract_citations` keeps a `[n]` marker only if `n` is one of those sources and removes the rest; code blocks are left alone because `items[1]` is an index, not a citation. Each kept citation stores the repository, file, line range and first lines. The web app renders citation chips only for citations the server returned, and links them to `#L<start>-L<end>` in the code view. The local answerer additionally refuses to answer when no retrieved source shares a word with the question.

## Consequences

- A model that cites a real source but misreads it is not caught; the reader can check, because the lines are one click away.
- Retrieval quality bounds answer quality: a relevant file that was not retrieved cannot be cited.

## Alternatives considered

Trusting the model's markers; asking the model for quotes and string-matching them (brittle across whitespace and formatting)..
