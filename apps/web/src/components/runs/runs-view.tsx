"use client";

import { FlaskConical, Play } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";

import { RelativeTime } from "@/components/domain/relative-time";
import { RunStatusBadge } from "@/components/domain/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar } from "@/components/ui/filter-bar";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Pagination } from "@/components/ui/pagination";
import { TableContainer, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDuration } from "@/lib/format";
import { RUN_TRIGGER } from "@/lib/labels";
import { wsPath } from "@/lib/navigation";
import { useRepositories, useRuns, useStartRun } from "@/lib/queries";
import { useUrlParams } from "@/lib/use-url-params";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";

const PAGE_SIZE = 25;

function RunsBody() {
  const { slug } = useActiveWorkspace();
  const router = useRouter();
  const canRun = useCan("developer");
  const { get, update } = useUrlParams();
  const repository = get("repo") ?? "";
  const status = get("status") ?? "";
  const offset = Number(get("offset") ?? 0) || 0;
  const runs = useRuns(slug, {
    repository: repository || undefined,
    status: status || undefined,
    limit: PAGE_SIZE,
    offset,
  });
  const repositories = useRepositories(slug, { status: "ready", limit: 100 });
  const start = useStartRun(slug);
  const target = repository || repositories.data?.items.find((r) => r.status === "ready")?.slug;
  const empty = runs.data && runs.data.total === 0 && !repository && !status;

  return (
    <PageBody>
      <PageHeader
        title="Test runs"
        description="Every run happens in a throwaway sandbox: no network, capped CPU and memory, a time limit."
        actions={
          canRun && target ? (
            <Button
              loading={start.isPending}
              onClick={async () => {
                const run = await start.mutateAsync(target);
                toast.success(`Test run #${run.number} queued`);
                router.push(wsPath(slug, "runs", String(run.number)));
              }}
            >
              <Play /> Run tests{repository ? "" : target ? ` in ${target}` : ""}
            </Button>
          ) : null
        }
      />
      {empty ? null : (
        <FilterBar className="mb-4">
          <NativeSelect
            aria-label="Repository"
            value={repository}
            onChange={(event) => update({ repo: event.target.value, offset: null })}
            className="w-auto min-w-40"
          >
            <option value="">All repositories</option>
            {repositories.data?.items.map((r) => (
              <option key={r.id} value={r.slug}>
                {r.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            aria-label="Status"
            value={status}
            onChange={(event) => update({ status: event.target.value, offset: null })}
            className="w-auto min-w-36"
          >
            <option value="">Any status</option>
            {["passed", "failed", "error", "timed_out", "running", "queued"].map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ")}
              </option>
            ))}
          </NativeSelect>
        </FilterBar>
      )}
      {runs.error ? (
        <ErrorState message={runs.error.message} onRetry={() => runs.refetch()} />
      ) : !runs.data ? (
        <Skeleton className="h-72" />
      ) : empty ? (
        <Card>
          <EmptyState
            icon={<FlaskConical />}
            title="No test runs yet"
            description="Run a repository's tests, or let the agent run them while it works on a task."
          />
        </Card>
      ) : runs.data.items.length === 0 ? (
        <Card>
          <EmptyState title="No run matches" description="Change the filters to see more." />
        </Card>
      ) : (
        <>
          <Card className="overflow-hidden">
            <TableContainer label="Test runs">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead>Repository</TableHead>
                    <TableHead>Trigger</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead className="text-right">Duration</TableHead>
                    <TableHead className="text-right">When</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.data.items.map((run) => (
                    <TableRow key={run.id}>
                      <TableCell>
                        <Link href={wsPath(slug, "runs", String(run.number))} className="font-medium hover:underline">
                          #{run.number}
                        </Link>
                      </TableCell>
                      <TableCell>{run.repository}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {RUN_TRIGGER[run.trigger] ?? run.trigger}
                        {run.task_number ? (
                          <Link
                            href={wsPath(slug, "tasks", String(run.task_number))}
                            className="text-primary ml-1.5 underline underline-offset-2"
                          >
                            task #{run.task_number}
                          </Link>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <span className="flex items-center gap-2">
                          <RunStatusBadge status={run.status} />
                          {run.total ? (
                            <span className="text-muted-foreground tabular text-[12.5px]">
                              {run.passed}/{run.total} passed
                            </span>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell className="tabular text-right">
                        {run.duration_ms ? formatDuration(run.duration_ms) : "-"}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-right">
                        <RelativeTime iso={run.created_at} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Card>
          {runs.data.total > PAGE_SIZE ? (
            <Pagination
              className="mt-4"
              total={runs.data.total}
              limit={PAGE_SIZE}
              offset={offset}
              onOffsetChange={(next) => update({ offset: next || null })}
              noun="runs"
            />
          ) : null}
        </>
      )}
    </PageBody>
  );
}

export function RunsView() {
  return (
    <Suspense>
      <RunsBody />
    </Suspense>
  );
}
