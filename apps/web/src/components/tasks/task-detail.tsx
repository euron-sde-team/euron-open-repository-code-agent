"use client";

import { RefreshCw, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Markdown } from "@/components/domain/markdown";
import { RelativeTime } from "@/components/domain/relative-time";
import { PatchStatusBadge, TaskStatusBadge } from "@/components/domain/status-badge";
import { CommentComposer, DiffViewer } from "@/components/tasks/diff-viewer";
import { ReviewCard } from "@/components/tasks/review-card";
import { TestComparison } from "@/components/tasks/test-comparison";
import { Trace } from "@/components/tasks/trace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, ErrorState, Skeleton, Spinner } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { SKILL_LABEL } from "@/lib/labels";
import { wsPath } from "@/lib/navigation";
import { useCancelTask, usePatch, useRetryTask, useTask } from "@/lib/queries";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";
import { groupComments } from "@/lib/diff";

const RETRYABLE = new Set(["failed", "rejected", "awaiting_review", "cancelled"]);

function PatchSection({ taskNumber, patchId }: { taskNumber: number; patchId: string }) {
  const { slug } = useActiveWorkspace();
  const canComment = useCan("developer");
  const patch = usePatch(slug, patchId);
  const task = useTask(slug, taskNumber);
  if (patch.error) return <ErrorState message={patch.error.message} onRetry={() => patch.refetch()} />;
  if (!patch.data || !task.data) return <Skeleton className="h-96" />;
  const data = patch.data;
  const editable = canComment && (data.status === "proposed" || data.status === "approved");
  const general = groupComments(data.comments).general;
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-5">
        <section aria-label="Why this change">
          <h2 className="text-[15px] font-semibold tracking-tight">{data.summary}</h2>
          <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-[12.5px]">
            <Badge tone="outline">{SKILL_LABEL[data.skill] ?? data.skill}</Badge>
            <span>
              by the <span className="font-medium">{data.planner}</span> planner
            </span>
            <span className="tabular">
              <span className="text-success font-medium">+{data.additions}</span>{" "}
              <span className="text-danger font-medium">-{data.deletions}</span> in {data.files.length} file
              {data.files.length === 1 ? "" : "s"}
            </span>
          </div>
          {data.rationale ? <Markdown text={data.rationale} className="mt-3" /> : null}
        </section>
        <DiffViewer patch={data} canComment={editable} />
        <section aria-label="Discussion" className="space-y-3">
          <h3 className="text-[14px] font-semibold tracking-tight">Discussion</h3>
          {general.length === 0 ? (
            <p className="text-muted-foreground text-[13px]">
              No general comments. Line comments appear in the diff above.
            </p>
          ) : null}
          {general.map((comment) => (
            <div key={comment.id} className="border-border bg-card rounded-lg border px-3 py-2 text-[13px] shadow-sm">
              <div className="flex items-center gap-2">
                <span className="font-medium">{comment.author ?? "Someone"}</span>
                <RelativeTime iso={comment.created_at} className="text-subtle text-[12px]" />
                {comment.resolved ? <Badge tone="success">Resolved</Badge> : null}
              </div>
              <p className="mt-1 break-words whitespace-pre-wrap">{comment.body}</p>
            </div>
          ))}
          {editable ? <CommentComposer patchId={data.id} placeholder="Comment on the change as a whole" /> : null}
        </section>
      </div>
      <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start" aria-label="Review">
        <ReviewCard patch={data} task={task.data} />
        <Card>
          <CardHeader>
            <CardTitle>Tests</CardTitle>
          </CardHeader>
          <CardContent>
            <TestComparison baseline={data.baseline_run} verify={data.verify_run} workspace={slug} />
          </CardContent>
        </Card>
        {data.plan.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>Plan</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="list-decimal space-y-2 pl-5 text-[13px]">
                {data.plan.map((step) => (
                  <li key={step.title}>
                    <span className="font-medium">{step.title}</span>
                    {step.detail ? (
                      <span className="text-muted-foreground block text-[12.5px]">{step.detail}</span>
                    ) : null}
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        ) : null}
      </aside>
    </div>
  );
}

export function TaskDetailView({ number }: { number: number }) {
  const { slug } = useActiveWorkspace();
  const canRetry = useCan("developer");
  const task = useTask(slug, number);
  const retry = useRetryTask(slug, number);
  const cancel = useCancelTask(slug, number);
  const [chosen, setChosen] = useState<string | null>(null);

  if (task.error) return <ErrorState message={task.error.message} onRetry={() => task.refetch()} className="py-24" />;
  const data = task.data;
  if (!data) {
    return (
      <PageBody>
        <Skeleton className="h-8 w-80" />
        <Skeleton className="mt-6 h-96" />
      </PageBody>
    );
  }
  const patchId = chosen && data.patches.some((p) => p.id === chosen) ? chosen : (data.patches[0]?.id ?? null);
  const working = data.status === "queued" || data.status === "running";

  return (
    <PageBody className="max-w-7xl">
      <PageHeader
        title={
          <>
            <span className="text-subtle tabular font-normal">#{data.number}</span> {data.title}
          </>
        }
        documentTitle={`Task #${data.number}: ${data.title}`}
        breadcrumbs={[{ label: "Tasks", href: wsPath(slug, "tasks") }, { label: `#${data.number}` }]}
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link
              href={wsPath(slug, "repos", encodeURIComponent(data.repository))}
              className="hover:text-foreground font-medium hover:underline"
            >
              {data.repository}
            </Link>
            {data.requested_by ? <span>asked by {data.requested_by}</span> : null}
            <RelativeTime iso={data.created_at} />
            {data.base_commit ? (
              <code className="bg-muted rounded px-1 font-mono text-[11.5px]">{data.base_commit.slice(0, 8)}</code>
            ) : null}
          </span>
        }
        actions={
          <>
            <TaskStatusBadge status={data.status} />
            {canRetry && RETRYABLE.has(data.status) ? (
              <Button
                variant="secondary"
                size="sm"
                loading={retry.isPending}
                onClick={async () => {
                  await retry.mutateAsync(undefined);
                  toast.success("Queued for a new revision");
                }}
              >
                <RefreshCw /> Retry
              </Button>
            ) : null}
            {canRetry && data.status === "queued" ? (
              <Button variant="secondary" size="sm" loading={cancel.isPending} onClick={() => cancel.mutate()}>
                <XCircle /> Cancel
              </Button>
            ) : null}
          </>
        }
      />

      {data.status === "failed" ? (
        <ErrorNotice message={data.error ?? "The agent could not produce a change."} className="mb-5" />
      ) : null}
      {working ? (
        <p
          className="bg-info-soft text-info mb-5 flex items-center gap-2 rounded-lg px-3 py-2 text-[13px]"
          role="status"
        >
          <Spinner className="text-info size-3.5" />
          {data.status === "queued"
            ? "Waiting for a worker."
            : "The agent is working: reading the code, running the tests, writing the change."}
        </p>
      ) : null}

      {data.description ? (
        <Card className="mb-5">
          <CardContent className="py-3.5">
            <p className="text-muted-foreground mb-1 text-[11.5px] font-medium tracking-wider uppercase">Request</p>
            <p className="text-[13.5px] break-words whitespace-pre-wrap">{data.description}</p>
          </CardContent>
        </Card>
      ) : null}

      {data.patches.length > 1 ? (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <SegmentedControl
            label="Revision"
            value={patchId ?? ""}
            onValueChange={setChosen}
            options={data.patches.map((p) => ({ value: p.id, label: `Revision ${p.revision}` }))}
          />
          {data.patches.find((p) => p.id === patchId) ? (
            <PatchStatusBadge status={data.patches.find((p) => p.id === patchId)!.status} />
          ) : null}
        </div>
      ) : null}

      {patchId ? (
        <PatchSection taskNumber={data.number} patchId={patchId} key={patchId} />
      ) : data.status === "failed" || working ? null : (
        <Card>
          <EmptyState title="No patch yet" description="The agent has not proposed a change for this task." />
        </Card>
      )}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Agent trace</CardTitle>
        </CardHeader>
        <CardContent>
          <Trace events={data.trace} />
        </CardContent>
      </Card>
    </PageBody>
  );
}
