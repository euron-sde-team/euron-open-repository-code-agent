import Link from "next/link";
import type { ReactNode } from "react";

import { blocks, inlineSegments } from "@/lib/citations";
import { cn } from "@/lib/cn";
import { codePath } from "@/lib/navigation";
import type { Citation } from "@/lib/types";

/**
 * The small Markdown subset answers and READMEs use, rendered as React nodes (never as
 * HTML). `[n]` markers become chips that open the cited lines when `citations` knows `n`.
 */
export function Markdown({
  text,
  workspace,
  citations = [],
  className,
}: {
  text: string;
  workspace?: string;
  citations?: Citation[];
  className?: string;
}) {
  const byNumber = new Map(citations.map((c) => [c.n, c]));

  function inline(line: string): ReactNode[] {
    return inlineSegments(line).map((segment, index) => {
      switch (segment.kind) {
        case "code":
          return (
            <code key={index} className="bg-muted rounded px-1 py-0.5 font-mono text-[0.92em]">
              {segment.text}
            </code>
          );
        case "bold":
          return (
            <strong key={index} className="font-semibold">
              {segment.text}
            </strong>
          );
        case "cite": {
          const citation = byNumber.get(segment.n);
          if (!citation || !workspace) return <span key={index}>[{segment.n}]</span>;
          return (
            <Link
              key={index}
              href={codePath(workspace, citation.repository, citation.path, citation.start_line, citation.end_line)}
              title={`${citation.path}:${citation.start_line}-${citation.end_line}`}
              aria-label={`Source ${segment.n}: ${citation.path}, lines ${citation.start_line} to ${citation.end_line}`}
              className="bg-accent text-accent-foreground hover:bg-primary hover:text-primary-foreground mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded px-1 align-baseline text-[11px] font-semibold no-underline transition-colors"
            >
              {segment.n}
            </Link>
          );
        }
        default:
          return <span key={index}>{segment.text}</span>;
      }
    });
  }

  return (
    <div className={cn("space-y-3 text-[14px] leading-relaxed break-words", className)}>
      {blocks(text).map((block, index) => {
        switch (block.kind) {
          case "heading":
            return (
              <p
                key={index}
                className={cn("font-semibold tracking-tight", block.level <= 2 ? "pt-1 text-[16px]" : "text-[14.5px]")}
              >
                {inline(block.text)}
              </p>
            );
          case "list":
            return (
              <ul key={index} className="list-disc space-y-1.5 pl-5">
                {block.items.map((item, i) => (
                  <li key={i}>{inline(item)}</li>
                ))}
              </ul>
            );
          case "code":
            return (
              <pre
                key={index}
                tabIndex={0}
                className="bg-code border-border scroll-quiet overflow-x-auto rounded-lg border p-3 font-mono text-[12.5px] leading-relaxed"
              >
                <code>{block.text}</code>
              </pre>
            );
          default:
            return <p key={index}>{inline(block.text)}</p>;
        }
      })}
    </div>
  );
}
