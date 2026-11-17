"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { PlainSnippet } from "@/components/domain/code-lines";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/feedback";
import { formatNumber } from "@/lib/format";
import { codePath } from "@/lib/navigation";
import type { SemanticSearch, SymbolSearch, TextSearch } from "@/lib/types";

/** The matched ranges of a line wrapped in <mark>; the text itself is rendered as nodes. */
export function Highlighted({ text, ranges }: { text: string; ranges: [number, number][] }) {
  const parts: ReactNode[] = [];
  let cursor = 0;
  ranges.forEach(([start, end], index) => {
    if (start > cursor) parts.push(text.slice(cursor, start));
    parts.push(
      <mark key={index} className="bg-highlight text-foreground rounded-sm px-0.5">
        {text.slice(start, end)}
      </mark>,
    );
    cursor = end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}

export function SymbolResults({ data, workspace }: { data: SymbolSearch; workspace: string }) {
  if (data.hits.length === 0) {
    return (
      <EmptyState title="No symbol matches" description="Try a shorter name, or search the text of the code instead." />
    );
  }
  return (
    <ul className="space-y-2">
      {data.hits.map((hit) => (
        <li key={hit.id}>
          <Card className="hover:border-input transition-colors">
            <Link
              href={codePath(workspace, hit.repository, hit.path, hit.start_line, hit.end_line)}
              className="block px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="primary">{hit.kind}</Badge>
                <span className="font-mono text-[13.5px] font-semibold break-all">{hit.qualified_name}</span>
                {hit.is_test ? (
                  <Badge tone="info">
                    <FlaskConical /> test
                  </Badge>
                ) : null}
                <span className="text-subtle tabular ml-auto text-[12px]">{formatNumber(hit.ref_count)} refs</span>
              </div>
              {hit.signature ? (
                <p className="text-muted-foreground mt-1 truncate font-mono text-[12.5px]">{hit.signature}</p>
              ) : null}
              {hit.doc ? <p className="text-muted-foreground mt-1 line-clamp-1 text-[13px]">{hit.doc}</p> : null}
              <p className="text-subtle mt-1.5 font-mono text-[12px]">
                {hit.repository} / {hit.path}:{hit.start_line}
              </p>
            </Link>
          </Card>
        </li>
      ))}
    </ul>
  );
}

export function TextResults({ data, workspace }: { data: TextSearch; workspace: string }) {
  if (data.files.length === 0) {
    return (
      <EmptyState
        title="No line matches"
        description={
          data.regex
            ? "Check the expression, or relax the path filter."
            : "Try fewer words, or switch to a regular expression."
        }
      />
    );
  }
  return (
    <div className="space-y-3">
      {data.files.map((file) => (
        <Card key={`${file.repository}:${file.path}`} className="overflow-hidden">
          <div className="border-border bg-muted/50 flex items-center justify-between gap-3 border-b px-4 py-2">
            <Link
              href={codePath(workspace, file.repository, file.path)}
              className="min-w-0 truncate font-mono text-[12.5px] font-medium hover:underline"
            >
              <span className="text-muted-foreground">{file.repository} / </span>
              {file.path}
            </Link>
            <span className="text-subtle tabular shrink-0 text-[12px]">{file.matches.length} lines</span>
          </div>
          <ul className="bg-code py-1 font-mono text-[12.5px]">
            {file.matches.map((match) => (
              <li key={match.line}>
                <Link
                  href={codePath(workspace, file.repository, file.path, match.line)}
                  className="hover:bg-code-line flex gap-3 px-4 py-0.5"
                >
                  <span className="text-subtle tabular w-10 shrink-0 text-right">{match.line}</span>
                  <span className="min-w-0 break-all whitespace-pre-wrap">
                    <Highlighted text={match.text} ranges={match.ranges} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      ))}
      {data.truncated ? (
        <p className="text-muted-foreground text-center text-[13px]">
          Showing the first {formatNumber(data.match_count)} matches. Narrow the search with a path or a more specific
          pattern.
        </p>
      ) : null}
    </div>
  );
}

export function SemanticResults({ data, workspace }: { data: SemanticSearch; workspace: string }) {
  if (data.hits.length === 0) {
    return <EmptyState title="Nothing close enough" description="Describe what the code does in other words." />;
  }
  return (
    <ul className="space-y-3">
      {data.hits.map((hit, index) => (
        <li key={`${hit.path}:${hit.start_line}`}>
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
              <span className="text-subtle tabular text-[12px]">{index + 1}</span>
              {hit.symbol ? <span className="font-mono text-[13px] font-semibold break-all">{hit.symbol}</span> : null}
              {hit.kind ? <Badge tone="primary">{hit.kind}</Badge> : null}
              <Link
                href={codePath(workspace, hit.repository, hit.path, hit.start_line, hit.end_line)}
                className="text-muted-foreground hover:text-foreground ml-auto font-mono text-[12px] hover:underline"
              >
                {hit.repository} / {hit.path}:{hit.start_line}-{hit.end_line}
              </Link>
            </div>
            <div className="px-3 pt-2 pb-3">
              <PlainSnippet text={hit.snippet} firstLine={hit.start_line} />
            </div>
          </Card>
        </li>
      ))}
    </ul>
  );
}
