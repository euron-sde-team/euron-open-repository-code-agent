"use client";

import { ChevronDown, Download, Terminal } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { RelativeTime } from "@/components/domain/relative-time";
import { CaseStatusBadge, RunStatusBadge } from "@/components/domain/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, ErrorState, Skeleton, Spinner } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { StatCard } from "@/components/ui/stat-card";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiUrl, ws } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import { RUN_TRIGGER } from "@/lib/labels";
import { codePath, wsPath } from "@/lib/navigation";
import { useRun } from "@/lib/queries";
import type { TestCase } from "@/lib/types";
import { useActiveWorkspace } from "@/lib/workspace-context";

function CaseRow({ test, repository, workspace }: { test: TestCase; repository: string; workspace: string }) {
  const [open, setOpen] = useState(test.status === "failed" || test.status === "error");
  const failing = test.status === "failed" || test.status === "error";
  return (
    <>
      <TableRow>
        <TableCell className="max-w-0">
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            disabled={!test.message}
            className="flex w-full items-center gap-2 text-left"
          >
            <ChevronDown
              className={cn(
                "text-subtle size-3.5 shrink-0 transition-transform",
                !open && "-rotate-90",
                !test.message && "invisible",
              )}
              aria-hidden
            />
            <span className="min-w-0 truncate font-mono text-[12.5px]">{test.name}</span>
          </button>
        </TableCell>
        <TableCell className="text-muted-foreground max-w-0 truncate font-mono text-[12px]">
          {test.file ? (
            <Link
              href={codePath(workspace, repository, test.file, test.line ?? undefined)}
              className="hover:text-foreground hover:underline"
            >
              {test.file}
              {test.line ? `:${test.line}` : ""}
            </Link>
          ) : (
            test.classname
          )}
        </TableCell>
        <TableCell>
          <CaseStatusBadge status={test.status} />
        </TableCell>
        <TableCell className="tabular text-right">{formatDuration(test.duration_ms)}</TableCell>
      </TableRow>
      {open && test.message ? (
        <TableRow className={failing ? "bg-danger-soft/40" : ""}>
          <TableCell colSpan={4} className="py-2">
            <pre className="font-mono text-[12px] leading-relaxed break-words whitespace-pre-wrap">{test.message}</pre>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  );
}

export function RunDetailView({ number }: { number: number }) {
  const { slug } = useActiveWorkspace();
  const run = useRun(slug, number);
  const [filter, setFilter] = useState<"all" | "failing">("all");

  if (run.error) return <ErrorState message={run.error.message} onRetry={() => run.refetch()} className="py-24" />;
  const data = run.data;
  if (!data) {
    return (
      <PageBody>
        <Skeleton className="h-8 w-72" />
        <Skeleton className="mt-6 h-96" />
      </PageBody>
    );
  }
  const live = data.status === "queued" || data.status === "running";
  const failing = data.results.filter((t) => t.status === "failed" || t.status === "error");
  const shown = filter === "failing" ? failing : data.results;

  return (
    <PageBody>
      <PageHeader
        title={`Test run #${data.number}`}
        breadcrumbs={[{ label: "Test runs", href: wsPath(slug, "runs") }, { label: `#${data.number}` }]}
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link
              href={wsPath(slug, "repos", encodeURIComponent(data.repository))}
              className="hover:text-foreground font-medium hover:underline"
            >
              {data.repository}
            </Link>
            <span>{RUN_TRIGGER[data.trigger] ?? data.trigger}</span>
            {data.task_number ? (
              <Link href={wsPath(slug, "tasks", String(data.task_number))} className="text-primary hover:underline">
                task #{data.task_number}
              </Link>
            ) : null}
            {data.commit_sha ? (
              <code className="bg-muted rounded px-1 font-mono text-[11.5px]">{data.commit_sha.slice(0, 8)}</code>
            ) : null}
            <RelativeTime iso={data.created_at} />
          </span>
        }
        actions={<RunStatusBadge status={data.status} />}
      />

      {live ? (
        <p
          className="bg-info-soft text-info mb-5 flex items-center gap-2 rounded-lg px-3 py-2 text-[13px]"
          role="status"
        >
          <Spinner className="text-info size-3.5" />{" "}
          {data.status === "queued" ? "Waiting for a worker." : "Running in the sandbox."}
        </p>
      ) : null}
      {data.error ? <ErrorNotice message={data.error} className="mb-5" /> : null}

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Passed"
          value={`${data.passed} / ${data.total}`}
          caption={data.skipped ? `${data.skipped} skipped` : "Every test counted"}
        />
        <StatCard
          label="Failing"
          value={data.failed + data.errors}
          caption={data.failed + data.errors ? `${data.failed} failed, ${data.errors} errors` : "No failures"}
        />
        <StatCard
          label="Duration"
          value={data.duration_ms ? formatDuration(data.duration_ms) : "-"}
          caption={data.exit_code !== null ? `Exit code ${data.exit_code}` : "Not finished"}
        />
        <StatCard label="Sandbox" value={data.backend ?? "-"} caption={data.image ?? "Resource-limited process"} />
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Terminal className="text-muted-foreground size-4" aria-hidden /> Command
          </CardTitle>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(data.limits).map(([key, value]) => (
              <Badge key={key} tone="outline">
                {key.replace("_", " ")}: {String(value)}
                {key === "timeout_s" ? " s" : key === "memory_mb" ? " MB" : ""}
              </Badge>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          <code className="bg-code border-border block overflow-x-auto rounded-lg border px-3 py-2 font-mono text-[12.5px]">
            {data.command}
          </code>
        </CardContent>
      </Card>

      <Card className="mb-6 overflow-hidden">
        <CardHeader>
          <CardTitle>Results</CardTitle>
          {failing.length > 0 ? (
            <SegmentedControl
              label="Show tests"
              size="sm"
              value={filter}
              onValueChange={setFilter}
              options={[
                { value: "all", label: `All ${data.results.length}` },
                { value: "failing", label: `Failing ${failing.length}` },
              ]}
            />
          ) : null}
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {data.results.length === 0 ? (
            <EmptyState
              title={live ? "Waiting for results" : "No per-test results"}
              description={
                live
                  ? "They appear when the run finishes."
                  : "The command did not produce a test report. The log has the details."
              }
              className="py-8"
            />
          ) : (
            <TableContainer label="Test results">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Test</TableHead>
                    <TableHead>File</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead className="text-right">Time</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shown.map((test) => (
                    <CaseRow
                      key={`${test.classname}.${test.name}`}
                      test={test}
                      repository={data.repository}
                      workspace={slug}
                    />
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Log</CardTitle>
          {data.has_full_log ? (
            <Button asChild variant="secondary" size="sm">
              <a href={apiUrl(`${ws(slug)}/test-runs/${data.number}/log`)} download={`run-${data.number}.log`}>
                <Download /> Full log
              </a>
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {data.log_tail ? (
            <>
              <pre className="bg-code border-border scroll-quiet max-h-[28rem] overflow-auto rounded-lg border p-3 font-mono text-[12px] leading-relaxed break-words whitespace-pre-wrap">
                {data.log_tail}
              </pre>
              {data.log_truncated ? (
                <p className="text-subtle mt-2 text-[12px]">
                  The log was cut at the deployment&apos;s limit; this is its end.
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-muted-foreground text-[13px]">
              {live ? "No output yet." : "The run produced no output."}
            </p>
          )}
        </CardContent>
      </Card>
    </PageBody>
  );
}
