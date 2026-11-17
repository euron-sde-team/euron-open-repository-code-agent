"use client";

import { useQueryClient } from "@tanstack/react-query";
import { History, MessageSquareCode, Plus, SendHorizontal, Square, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { AnswerCard, QuestionBubble } from "@/components/ask/message-card";
import { RelativeTime } from "@/components/domain/relative-time";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ApiError } from "@/lib/api";
import { streamAnswer } from "@/lib/ask-stream";
import { cn } from "@/lib/cn";
import { wsPath } from "@/lib/navigation";
import {
  qk,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useMessages,
  useRepositories,
} from "@/lib/queries";
import type { Conversation, Message, Source } from "@/lib/types";
import { useDocumentTitle } from "@/lib/use-document-title";
import { useActiveWorkspace } from "@/lib/workspace-context";

const SUGGESTIONS = [
  "What does this codebase do, and where does it start?",
  "Where is the main data model defined?",
  "Which tests cover the pricing logic?",
  "Who calls the function that calculates totals?",
];

type Pending = { question: string; text: string; sources: Source[] };

function ConversationList({
  conversations,
  activeId,
  workspace,
  onNavigate,
  onDelete,
}: {
  conversations: Conversation[] | undefined;
  activeId: string | null;
  workspace: string;
  onNavigate?: () => void;
  onDelete: (conversation: Conversation) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <Button asChild variant="secondary" size="sm" className="mb-3 w-full">
        <Link href={wsPath(workspace, "ask")} onClick={onNavigate}>
          <Plus /> New question
        </Link>
      </Button>
      <nav aria-label="Conversations" className="scroll-quiet min-h-0 flex-1 overflow-y-auto">
        {!conversations ? (
          <div className="space-y-2" aria-busy>
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : conversations.length === 0 ? (
          <p className="text-muted-foreground px-1 text-[13px]">Your conversations appear here.</p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((conversation) => (
              <li key={conversation.id} className="group relative">
                <Link
                  href={wsPath(workspace, "ask", conversation.id)}
                  onClick={onNavigate}
                  aria-current={conversation.id === activeId ? "page" : undefined}
                  className={cn(
                    "block rounded-lg px-2.5 py-2 pr-8 transition-colors",
                    conversation.id === activeId ? "bg-card ring-border shadow-sm ring-1" : "hover:bg-muted",
                  )}
                >
                  <span className="block truncate text-[13px] font-medium">{conversation.title}</span>
                  <span className="text-subtle block text-[11.5px]">
                    <RelativeTime iso={conversation.updated_at} />
                  </span>
                </Link>
                <button
                  type="button"
                  aria-label={`Delete ${conversation.title}`}
                  onClick={() => onDelete(conversation)}
                  className="text-subtle hover:text-danger absolute top-2 right-1.5 rounded-md p-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
}

export function AskView() {
  const { slug, can } = useActiveWorkspace();
  const router = useRouter();
  const client = useQueryClient();
  const params = useParams<{ id?: string[] }>();
  const routeId = params.id?.[0] ?? null;
  const conversations = useConversations(slug);
  const repositories = useRepositories(slug, { status: "ready", limit: 100 });
  const create = useCreateConversation(slug);
  const remove = useDeleteConversation(slug);
  // The conversation a stream is writing to; it can differ from the route until it ends.
  const [activeId, setActiveId] = useState<string | null>(routeId);
  const messages = useMessages(slug, routeId);
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const title = conversations.data?.find((c) => c.id === routeId)?.title;
  useDocumentTitle(title ?? "Ask");

  // A different conversation was opened: start from its state, not the previous one's.
  const [seenRoute, setSeenRoute] = useState(routeId);
  if (seenRoute !== routeId) {
    setSeenRoute(routeId);
    setActiveId(routeId);
    setPending(null);
    setError(null);
  }

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.data?.length, pending?.text]);

  async function send(text: string) {
    const asked = text.trim();
    if (!asked || pending) return;
    setError(null);
    setQuestion("");
    setPending({ question: asked, text: "", sources: [] });
    const controller = new AbortController();
    abort.current = controller;
    try {
      let id = activeId;
      if (!id) {
        const created = await create.mutateAsync({ repository: scope || undefined });
        id = created.id;
        setActiveId(id);
      }
      const answer = await streamAnswer(
        slug,
        { question: asked },
        id,
        {
          onSources: (sources) => setPending((p) => (p ? { ...p, sources } : p)),
          onDelta: (delta) => setPending((p) => (p ? { ...p, text: p.text + delta } : p)),
        },
        controller.signal,
      );
      const user: Message = {
        id: `local-${Date.now()}`,
        role: "user",
        content: asked,
        citations: [],
        sources: [],
        usage: null,
        created_at: new Date().toISOString(),
      };
      client.setQueryData<Message[]>(qk.messages(slug, id), (old) => [...(old ?? []), user, answer.message]);
      void client.invalidateQueries({ queryKey: qk.conversations(slug) });
      setPending(null);
      if (routeId !== id) router.replace(wsPath(slug, "ask", id));
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setPending(null);
        return;
      }
      setError(caught instanceof ApiError || caught instanceof Error ? caught.message : "The answer failed.");
      setQuestion(asked);
      setPending(null);
    } finally {
      abort.current = null;
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(question);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(question);
    }
  }

  const shown = routeId ? (messages.data ?? []) : [];
  const empty = shown.length === 0 && !pending;
  const noRepositories = repositories.data?.total === 0;

  return (
    <div className="flex h-full min-h-0">
      <aside className="border-border bg-sidebar hidden w-64 shrink-0 border-r p-3 lg:block" aria-label="History">
        <ConversationList
          conversations={conversations.data}
          activeId={routeId}
          workspace={slug}
          onDelete={setDeleting}
        />
      </aside>
      <Sheet open={history} onOpenChange={setHistory}>
        <SheetContent side="left" title="Conversations" className="w-[min(88vw,20rem)] p-3 pt-12">
          <ConversationList
            conversations={conversations.data}
            activeId={routeId}
            workspace={slug}
            onNavigate={() => setHistory(false)}
            onDelete={setDeleting}
          />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-border flex items-center gap-2 border-b px-4 py-2.5">
          <Button variant="secondary" size="sm" className="lg:hidden" onClick={() => setHistory(true)}>
            <History className="size-4" /> History
          </Button>
          <h1 className="min-w-0 truncate text-[15px] font-semibold tracking-tight">{title ?? "Ask the code"}</h1>
        </div>

        <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 sm:px-6">
            {empty ? (
              noRepositories ? (
                <EmptyState
                  icon={<MessageSquareCode />}
                  title="Index a repository first"
                  description="Answers come from the code CodeAgent has indexed. Connect a repository, then ask."
                  action={
                    <Button asChild variant="secondary">
                      <Link href={wsPath(slug, "repos")}>Go to repositories</Link>
                    </Button>
                  }
                />
              ) : (
                <div className="py-6 text-center">
                  <div className="bg-accent text-accent-foreground mx-auto mb-3 flex size-11 items-center justify-center rounded-xl">
                    <MessageSquareCode className="size-5" aria-hidden />
                  </div>
                  <h2 className="text-lg font-semibold tracking-tight">Ask about your code</h2>
                  <p className="text-muted-foreground mx-auto mt-1 max-w-md text-[13.5px]">
                    Name a function, class or file for the most precise answers. Every claim links to the lines it came
                    from.
                  </p>
                  <ul className="mx-auto mt-5 grid max-w-xl gap-2 sm:grid-cols-2">
                    {SUGGESTIONS.map((suggestion) => (
                      <li key={suggestion}>
                        <button
                          type="button"
                          onClick={() => setQuestion(suggestion)}
                          className="border-border bg-card hover:bg-muted h-full w-full rounded-xl border px-3 py-2.5 text-left text-[13px] shadow-sm transition-colors"
                        >
                          {suggestion}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            ) : null}

            {routeId && messages.isLoading ? <Skeleton className="h-40" /> : null}
            {shown.map((message) =>
              message.role === "user" ? (
                <QuestionBubble key={message.id} text={message.content} />
              ) : (
                <AnswerCard key={message.id} message={message} workspace={slug} />
              ),
            )}
            {pending ? (
              <>
                <QuestionBubble text={pending.question} />
                <AnswerCard
                  streaming
                  workspace={slug}
                  message={{
                    id: "pending",
                    role: "assistant",
                    content: pending.text,
                    citations: [],
                    sources: pending.sources,
                    usage: null,
                    created_at: "",
                  }}
                />
              </>
            ) : null}
            {error ? <ErrorNotice message={error} /> : null}
            <div ref={bottom} />
          </div>
        </div>

        <form onSubmit={onSubmit} className="border-border bg-background border-t px-4 py-3 sm:px-6">
          <div className="mx-auto flex max-w-3xl flex-col gap-2">
            <div className="flex items-end gap-2">
              <Textarea
                aria-label="Your question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
                maxLength={2000}
                placeholder={can("viewer") ? "Where is the tax for an invoice calculated?" : ""}
                className="max-h-40 min-h-[3.25rem] resize-none"
                disabled={Boolean(pending) || noRepositories}
              />
              {pending ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  aria-label="Stop"
                  onClick={() => abort.current?.abort()}
                >
                  <Square />
                </Button>
              ) : (
                <Button type="submit" size="icon" aria-label="Ask" disabled={!question.trim() || noRepositories}>
                  <SendHorizontal />
                </Button>
              )}
            </div>
            <div className="text-subtle flex flex-wrap items-center justify-between gap-2 text-[12px]">
              {routeId ? (
                <span>Follow-up questions use this conversation as context.</span>
              ) : (
                <label className="flex items-center gap-2">
                  Search in
                  <NativeSelect
                    aria-label="Repository scope"
                    value={scope}
                    onChange={(event) => setScope(event.target.value)}
                    className="h-7 w-auto py-0 text-[12px]"
                  >
                    <option value="">All ready repositories</option>
                    {repositories.data?.items.map((r) => (
                      <option key={r.id} value={r.slug}>
                        {r.name}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
              )}
              <span>Enter to send, Shift+Enter for a new line</span>
            </div>
          </div>
        </form>
      </div>

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this conversation?"
        description={deleting ? `"${deleting.title}" and its answers are deleted.` : ""}
        confirmLabel="Delete conversation"
        destructive
        onConfirm={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
          if (deleting.id === routeId) router.replace(wsPath(slug, "ask"));
        }}
      />
    </div>
  );
}
