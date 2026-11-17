"use client";

import { useEffect } from "react";

import { Tokens } from "@/components/domain/code-lines";
import { cn } from "@/lib/cn";
import { inRange } from "@/lib/lines";
import { parseLineHash } from "@/lib/navigation";
import { replaceHash } from "@/lib/use-hash";
import type { CodeLine } from "@/lib/types";

/**
 * A file with line numbers that are anchors: click one to select it, shift-click to extend
 * the range (`#L12-L30`). A range in the address bar is highlighted and scrolled into view
 * when the file loads, which is what a citation's link relies on.
 */
export function CodeView({ lines, hash, file }: { lines: CodeLine[]; hash: string; file: string }) {
  const range = parseLineHash(hash);

  useEffect(() => {
    if (!range) return;
    const target = document.getElementById(`L${range.start}`);
    // "center" keeps the cited lines clear of the sticky header on a short screen.
    target?.scrollIntoView({ block: "center" });
    // Only a new file or a new range should scroll; the hash string is the range.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, hash, lines.length]);

  function select(line: number, extend: boolean) {
    if (extend && range) {
      const start = Math.min(range.start, line);
      const end = Math.max(range.end, line);
      replaceHash(`#L${start}-L${end}`);
    } else {
      replaceHash(`#L${line}`);
    }
  }

  return (
    <pre
      tabIndex={0}
      className="bg-code scroll-quiet overflow-x-auto py-2 font-mono text-[12.5px] leading-[1.65]"
      aria-label={`Source of ${file}`}
    >
      <code className="block min-w-max">
        {lines.map((line, index) => {
          const number = index + 1;
          const selected = inRange(number, range);
          return (
            <span key={number} id={`L${number}`} className={cn("group flex scroll-mt-24", selected && "bg-code-line")}>
              <a
                href={`#L${number}`}
                onClick={(event) => {
                  event.preventDefault();
                  select(number, event.shiftKey);
                }}
                aria-label={`Line ${number}`}
                className={cn(
                  "tabular w-14 shrink-0 pr-3 text-right select-none",
                  selected ? "text-primary font-semibold" : "text-subtle hover:text-foreground",
                )}
              >
                {number}
              </a>
              <span className="pr-4 whitespace-pre">
                <Tokens tokens={line} />
                {line.length === 0 ? " " : null}
              </span>
            </span>
          );
        })}
      </code>
    </pre>
  );
}
