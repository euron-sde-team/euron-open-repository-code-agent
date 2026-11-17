"use client";

import { MessageSquarePlus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Tokens } from "@/components/domain/code-lines";
import { RelativeTime } from "@/components/domain/relative-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { CHANGE_LABEL, groupComments, lineKey, lineNumber, lineSide, orphaned } from "@/lib/diff";
import { useAddComment, useDeleteComment, useUpdateComment } from "@/lib/queries";
import type { DiffLine, Patch, PatchFile, ReviewComment } from "@/lib/types";
import { useActiveWorkspace } from "@/lib/workspace-context";

function CommentItem({ comment, patchId }: { comment: ReviewComment; patchId: string }) {
  const { slug, me, can } = useActiveWorkspace();
  const update = useUpdateComment(slug, patchId);
  const remove = useDeleteComment(slug, patchId);
  const mine = comment.author_id === me.user.id;
  return (
    <div
      className={cn(
        "border-border bg-card rounded-lg border px-3 py-2 text-[13px] shadow-sm",
        comment.resolved && "opacity-70",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{comment.author ?? "Someone"}</span>
        <RelativeTime iso={comment.created_at} className="text-subtle text-[12px]" />
        {comment.resolved ? <Badge tone="success">Resolved</Badge> : null}
        <span className="ml-auto flex gap-1">
          {mine || can("maintainer") ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[12px]"
              loading={update.isPending}
              onClick={() => update.mutate({ id: comment.id, resolved: !comment.resolved })}
            >
              {comment.resolved ? "Reopen" : "Resolve"}
            </Button>
          ) : null}
          {mine || can("owner") ? (
            <Button
              variant="danger-ghost"
              size="sm"
              className="h-6 px-2 text-[12px]"
              loading={remove.isPending}
              onClick={() => remove.mutate(comment.id)}
            >
              Delete
            </Button>
          ) : null}
        </span>
      </div>
      <p className="mt-1 break-words whitespace-pre-wrap">{comment.body}</p>
    </div>
  );
}

export function CommentComposer({
  patchId,
  anchor,
  onDone,
  placeholder = "Leave a comment",
  autoFocus,
}: {
  patchId: string;
  anchor?: { path: string; line: number; side: "old" | "new" };
  onDone?: () => void;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const { slug } = useActiveWorkspace();
  const add = useAddComment(slug, patchId);
  const [body, setBody] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    await add.mutateAsync({ body: body.trim(), ...anchor });
    setBody("");
    onDone?.();
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <Textarea
        aria-label={anchor ? `Comment on line ${anchor.line}` : "Comment on this patch"}
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder={placeholder}
        rows={2}
        maxLength={8000}
        autoFocus={autoFocus}
      />
      <div className="flex justify-end gap-2">
        {onDone ? (
          <Button type="button" variant="ghost" size="sm" onClick={onDone}>
            Cancel
          </Button>
        ) : null}
        <Button type="submit" size="sm" loading={add.isPending} disabled={!body.trim()}>
          Comment
        </Button>
      </div>
    </form>
  );
}

function DiffRow({
  file,
  line,
  comments,
  patchId,
  canComment,
}: {
  file: PatchFile;
  line: DiffLine;
  comments: ReviewComment[];
  patchId: string;
  canComment: boolean;
}) {
  const [composing, setComposing] = useState(false);
  const number = lineNumber(line);
  const side = lineSide(line);
  const sign = line.kind === "add" ? "+" : line.kind === "del" ? "-" : " ";
  return (
    <>
      <div className={cn("group flex", line.kind === "add" && "bg-diff-add", line.kind === "del" && "bg-diff-del")}>
        <span className="text-subtle tabular w-11 shrink-0 pr-2 text-right select-none" aria-hidden>
          {line.old_line ?? ""}
        </span>
        <span className="text-subtle tabular w-11 shrink-0 pr-2 text-right select-none" aria-hidden>
          {line.new_line ?? ""}
        </span>
        <span className="relative w-5 shrink-0 text-center select-none" aria-hidden>
          {sign}
        </span>
        <span className="min-w-0 flex-1 pr-4 whitespace-pre">
          <span className="sr-only">{line.kind === "add" ? "Added: " : line.kind === "del" ? "Removed: " : ""}</span>
          <Tokens tokens={line.tokens} />
          {line.tokens.length === 0 ? " " : null}
        </span>
        {canComment && number !== null ? (
          <button
            type="button"
            onClick={() => setComposing(true)}
            aria-label={`Comment on ${side === "old" ? "removed" : "new"} line ${number} of ${file.path}`}
            className="text-subtle hover:text-primary w-8 shrink-0 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 focus-visible:opacity-100"
          >
            <MessageSquarePlus className="mx-auto size-3.5" />
          </button>
        ) : null}
      </div>
      {comments.length > 0 || composing ? (
        <div className="bg-background border-border space-y-2 border-y px-4 py-2.5 font-sans whitespace-normal">
          {comments.map((comment) => (
            <CommentItem key={comment.id} comment={comment} patchId={patchId} />
          ))}
          {composing && number !== null ? (
            <CommentComposer
              patchId={patchId}
              anchor={{ path: file.path, line: number, side }}
              onDone={() => setComposing(false)}
              autoFocus
            />
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function FileDiff({
  file,
  byLine,
  fileComments,
  patchId,
  canComment,
}: {
  file: PatchFile;
  byLine: Map<string, ReviewComment[]>;
  fileComments: ReviewComment[];
  patchId: string;
  canComment: boolean;
}) {
  return (
    <section
      aria-label={`Changes to ${file.path}`}
      className="border-border bg-card overflow-hidden rounded-xl border shadow-sm"
    >
      <header className="border-border bg-muted/50 flex flex-wrap items-center gap-2 border-b px-4 py-2">
        <span className="min-w-0 flex-1 truncate font-mono text-[13px] font-medium">{file.path}</span>
        <Badge tone={file.change_type === "added" ? "success" : file.change_type === "deleted" ? "danger" : "neutral"}>
          {CHANGE_LABEL[file.change_type] ?? file.change_type}
        </Badge>
        <span className="tabular text-[12.5px] font-medium">
          <span className="text-success">+{file.additions}</span> <span className="text-danger">-{file.deletions}</span>
        </span>
      </header>
      {fileComments.length > 0 ? (
        <div className="border-border space-y-2 border-b px-4 py-2.5">
          {fileComments.map((comment) => (
            <CommentItem key={comment.id} comment={comment} patchId={patchId} />
          ))}
        </div>
      ) : null}
      <div
        tabIndex={0}
        role="region"
        aria-label={`Diff of ${file.path}`}
        className="bg-code scroll-quiet overflow-x-auto font-mono text-[12.5px] leading-[1.6]"
      >
        <div className="min-w-max">
          {file.hunks.map((hunk, index) => (
            <div key={`${hunk.old_start}-${hunk.new_start}-${index}`}>
              <div className="bg-diff-hunk text-muted-foreground px-4 py-1 text-[12px] whitespace-pre">
                @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@ {hunk.section}
              </div>
              {hunk.lines.map((line, i) => {
                const number = lineNumber(line);
                const key = number === null ? "" : lineKey(file.path, lineSide(line), number);
                return (
                  <DiffRow
                    key={`${line.old_line}-${line.new_line}-${i}`}
                    file={file}
                    line={line}
                    comments={key ? (byLine.get(key) ?? []) : []}
                    patchId={patchId}
                    canComment={canComment}
                  />
                );
              })}
            </div>
          ))}
          {file.hunks.length === 0 ? (
            <p className="text-muted-foreground px-4 py-3 text-[13px]">No textual changes.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/** The patch as a unified diff with syntax colours, and review comments anchored to lines. */
export function DiffViewer({ patch, canComment }: { patch: Patch; canComment: boolean }) {
  const { byLine, byFile } = groupComments(patch.comments);
  const lost = orphaned(patch.diff_files, patch.comments);
  return (
    <div className="space-y-4">
      {patch.diff_files.map((file) => (
        <FileDiff
          key={file.path}
          file={file}
          byLine={byLine}
          fileComments={[...(byFile.get(file.path) ?? []), ...lost.filter((c) => c.path === file.path)]}
          patchId={patch.id}
          canComment={canComment}
        />
      ))}
    </div>
  );
}
