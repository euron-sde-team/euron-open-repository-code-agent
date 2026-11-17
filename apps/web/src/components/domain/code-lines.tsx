import { cn } from "@/lib/cn";
import { tokenClass } from "@/lib/lines";
import type { Token } from "@/lib/types";

/** One line of highlighted code: text nodes only, so file content can never inject markup. */
export function Tokens({ tokens }: { tokens: Token[] }) {
  return (
    <>
      {tokens.map(([css, text], index) => (
        <span key={index} className={cn(tokenClass(css))}>
          {text}
        </span>
      ))}
    </>
  );
}

/**
 * A small block of highlighted code with line numbers starting at `firstLine`: symbol
 * previews and answer sources. Large files use the code view, which adds anchors and a
 * range selection.
 */
export function CodeSnippet({
  lines,
  firstLine = 1,
  className,
}: {
  lines: Token[][];
  firstLine?: number;
  className?: string;
}) {
  return (
    <pre
      className={cn(
        "bg-code border-border scroll-quiet overflow-x-auto rounded-lg border py-2 font-mono text-[12.5px] leading-[1.6]",
        className,
      )}
    >
      <code className="block min-w-max">
        {lines.map((line, index) => (
          <span key={index} className="flex">
            <span className="text-subtle tabular w-10 shrink-0 pr-3 text-right select-none">{firstLine + index}</span>
            <span className="pr-3 whitespace-pre">
              <Tokens tokens={line} />
              {line.length === 0 ? " " : null}
            </span>
          </span>
        ))}
      </code>
    </pre>
  );
}

/** Plain text as a code block (a source snippet the API returns without tokens). */
export function PlainSnippet({
  text,
  firstLine = 1,
  className,
}: {
  text: string;
  firstLine?: number;
  className?: string;
}) {
  return (
    <CodeSnippet
      lines={text.split("\n").map((line) => (line ? [["plain", line] as Token] : []))}
      firstLine={firstLine}
      className={className}
    />
  );
}
