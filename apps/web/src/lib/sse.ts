/** Server-sent events over fetch (POST bodies are not possible with EventSource). */

export type SseEvent = { event: string; data: unknown };

/** Parse as many complete events as the buffer holds; returns them and the unparsed rest. */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = [];
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length === 0) continue;
    try {
      events.push({ event, data: JSON.parse(data.join("\n")) });
    } catch {
      // A malformed frame is skipped; the stream carries on.
    }
  }
  return { events, rest };
}
