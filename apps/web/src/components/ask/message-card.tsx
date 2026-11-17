"use client";

import { ChevronDown, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PlainSnippet } from "@/components/domain/code-lines";
import { Markdown } from "@/components/domain/markdown";
import { cn } from "@/lib/cn";
import { formatDuration, formatNumber } from "@/lib/format";
import { codePath } from "@/lib/navigation";
import type { Citation, Message } from "@/lib/types";

function CitationRow({ citation, workspace }: { citation: Citation; workspace: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-border bg-card overflow-hidden rounded-lg border">
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="bg-accent text-accent-foreground flex size-5 shrink-0 items-center justify-center rounded text-[11px] font-semibold">
          {citation.n}
        </span>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <span className="min-w-0 truncate font-mono text-[12.5px]">
            {citation.path}
            <span className="text-subtle">
              :{citation.start_line}-{citation.end_line}
            </span>
          </span>
          {citation.symbol ? (
            <span className="text-muted-foreground hidden truncate text-[12px] sm:inline">{citation.symbol}</span>
          ) : null}
          <ChevronDown
            className={cn("text-subtle ml-auto size-4 shrink-0 transition-transform", open && "rotate-180")}
            aria-hidden
          />
        </button>
        <Link
          href={codePath(workspace, citation.repository, citation.path, citation.start_line, citation.end_line)}
          className="text-primary flex shrink-0 items-center gap-1 text-[12.5px] font-medium hover:underline"
          aria-label={`Open ${citation.path} at line ${citation.start_line}`}
        >
          Open <ExternalLink className="size-3" aria-hidden />
        </Link>
      </div>
      {open ? (
        <div className="border-border border-t p-2">
          <PlainSnippet text={citation.snippet} firstLine={citation.start_line} />
        </div>
      ) : null}
    </li>
  );
}

/** One answer: the text with its citation chips, the sources it stands on, and what it cost. */
export function AnswerCard({
  message,
  workspace,
  streaming = false,
}: {
  message: Message;
  workspace: string;
  streaming?: boolean;
}) {
  const usage = message.usage;
  return (
    <div className="space-y-3">
      <div className="border-border bg-card rounded-2xl rounded-tl-md border px-4 py-3 shadow-sm">
        <Markdown
          text={message.content || (streaming ? "Reading the code" : "")}
          workspace={workspace}
          citations={message.citations}
        />
        {streaming ? (
          <span
            className="bg-primary animate-pulse-dot mt-1 inline-block h-4 w-1.5 rounded-sm align-middle"
            aria-hidden
          />
        ) : null}
      </div>
      {message.citations.length > 0 ? (
        <section aria-label="Sources">
          <h3 className="text-muted-foreground mb-1.5 text-[11.5px] font-medium tracking-wider uppercase">
            Sources ({message.citations.length})
          </h3>
          <ul className="space-y-1.5">
            {message.citations.map((citation) => (
              <CitationRow key={citation.n} citation={citation} workspace={workspace} />
            ))}
          </ul>
        </section>
      ) : null}
      {usage ? (
        <p className="text-subtle text-[12px]">
          Answered by{" "}
          <span className="font-medium">
            {usage.answerer === "local" ? "the offline local answerer" : usage.answerer}
          </span>{" "}
          in {formatDuration(usage.latency_ms)}
          {usage.prompt_tokens + usage.completion_tokens > 0
            ? `, ${formatNumber(usage.prompt_tokens + usage.completion_tokens)} tokens`
            : ""}
          .
        </p>
      ) : null}
    </div>
  );
}

export function QuestionBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-tr-md px-4 py-2.5 text-[14px] break-words whitespace-pre-wrap">
        {text}
      </p>
    </div>
  );
}
