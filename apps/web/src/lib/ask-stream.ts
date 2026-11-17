import { ApiError, apiUrl, errorFrom, ws } from "@/lib/api";
import { parseSse } from "@/lib/sse";
import type { Answer, Source } from "@/lib/types";

export type AskHandlers = {
  onSources: (sources: Source[]) => void;
  onDelta: (text: string) => void;
};

/**
 * Ask a question and stream the answer. Resolves with the final message once the server
 * has verified its citations (the streamed text may still hold markers that were removed).
 */
export async function streamAnswer(
  workspace: string,
  body: { question: string; repository?: string },
  conversationId: string | null,
  handlers: AskHandlers,
  signal?: AbortSignal,
): Promise<Answer> {
  const path = conversationId
    ? `${ws(workspace)}/conversations/${conversationId}/messages/stream`
    : `${ws(workspace)}/ask/stream`;
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method: "POST",
      credentials: "include",
      signal,
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Cannot reach the CodeAgent API. Is it running?");
  }
  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    let parsed: unknown = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    throw errorFrom(response.status, parsed, response.headers.get("x-request-id"));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: Answer | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const parsed = parseSse(buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      if (event === "sources") handlers.onSources((data as { sources: Source[] }).sources);
      else if (event === "delta") handlers.onDelta((data as { text: string }).text);
      else if (event === "done") final = data as Answer;
      else if (event === "error") throw errorFrom(502, data, response.headers.get("x-request-id"));
    }
  }
  if (!final) throw new ApiError(502, "stream_incomplete", "The answer stopped before it finished.");
  return final;
}
