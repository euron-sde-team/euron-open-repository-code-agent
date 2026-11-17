/** Answers carry `[n]` markers; the renderer turns each into a link to its source. */

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "cite"; n: number };

const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\[(\d{1,2})\])/g;

/** Split one line of Markdown-ish text into plain, code, bold and citation segments. */
export function inlineSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) segments.push({ kind: "text", text: text.slice(last, index) });
    if (match[1]) segments.push({ kind: "code", text: match[1].slice(1, -1) });
    else if (match[2]) segments.push({ kind: "bold", text: match[2].slice(2, -2) });
    else segments.push({ kind: "cite", n: Number(match[4]) });
    last = index + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", text: text.slice(last) });
  return segments;
}

export type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "code"; text: string; language: string };

/** Headings, paragraphs, bullet lists and fenced code: all the structure answers and READMEs need. */
export function blocks(markdown: string): Block[] {
  const result: Block[] = [];
  const lines = markdown.split("\n");
  let paragraph: string[] = [];
  let list: string[] | null = null;
  const flush = () => {
    if (paragraph.length) result.push({ kind: "paragraph", text: paragraph.join(" ") });
    if (list) result.push({ kind: "list", items: list });
    paragraph = [];
    list = null;
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const fence = /^```(\w*)\s*$/.exec(line);
    if (fence) {
      flush();
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index] ?? "")) {
        body.push(lines[index] ?? "");
        index += 1;
      }
      result.push({ kind: "code", text: body.join("\n"), language: fence[1] ?? "" });
      continue;
    }
    const heading = /^(#{1,4})\s+(.*\S)\s*$/.exec(line);
    if (heading) {
      flush();
      result.push({ kind: "heading", level: (heading[1] ?? "#").length, text: heading[2] ?? "" });
      continue;
    }
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      if (paragraph.length) flush();
      list = [...(list ?? []), bullet[1] ?? ""];
      continue;
    }
    if (line.trim() === "") {
      flush();
      continue;
    }
    if (list) flush();
    paragraph.push(line.trim());
  }
  flush();
  return result;
}
