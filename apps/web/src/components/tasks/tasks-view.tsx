"use client";

import { GitPullRequestArrow, Plus } from "lucide-react";
import Link from "next/link";
import { Suspense, useState } from "react";

import { RelativeTime } from "@/components/domain/relative-time";
import { TaskStatusBadge } from "@/components/domain/status-badge";
import { NewTaskDialog } from "@/components/tasks/new-task-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Pagination } from "@/components/ui/pagination";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { SKILL_LABEL } from "@/lib/labels";
import { wsPath } from "@/lib/navigation";
import { useRepositories, useTasks } from "@/lib/queries";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";

const PAGE_SIZE = 20;
const VIEWS = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "awaiting_review", label: "Needs review" },
  { value: "applied", label: "Applied" },
  { value: "failed", label: "Failed" },
] as const;
type View = (typeof VIEWS)[number]["value"];

function TasksBody() {
  const { slug } = useActiveWorkspace();
  const canCreate = useCan("developer");
  const { get, update } = useUrlParams();
  const [creating, setCreating] = useState(false);
  const [text, setText] = useState(get("q") ?? "");
  const q = useDebouncedValue(text, 250);
  const raw = get("status") ?? "all";
  const view: View = VIEWS.some((v) => v.value === raw) ? (raw as View) : "all";
  const repository = get("repo") ?? "";
  const offset = Number(get("offset") ?? 0) || 0;
  const tasks = useTasks(slug, {
    status: view === "all" ? undefined : view,
    repository: repository || undefined,
    q: q || undefined,
    limit: PAGE_SIZE,
    offset,
  });
  const repositories = useRepositories(slug, { limit: 100 });
  const noFilters = view === "all" && !q && !repository;
  const empty = tasks.data && tasks.data.total === 0 && noFilters;

  return (
    <PageBody>
      <PageHeader
        title="Tasks"
        description="Describe a change. The agent proposes a patch with its tests, and a maintainer reviews it."
        actions={
          canCreate ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New task
            </Button>
          ) : null
        }
      />
      {empty ? null : (
        <FilterBar className="mb-4">
          <SegmentedControl<View>
            label="Task status"
            value={view}
            onValueChange={(next) => update({ status: next === "all" ? null : next, offset: null })}
            options={VIEWS.map((v) => ({ value: v.value, label: v.label }))}
          />
          <SearchField
            value={text}
            onChange={(value) => {
              setText(value);
              update({ q: value, offset: null });
            }}
            label="Search tasks"
          />
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
        </FilterBar>
      )}
      {tasks.error ? (
        <ErrorState message={tasks.error.message} onRetry={() => tasks.refetch()} />
      ) : !tasks.data ? (
        <div className="space-y-2" aria-busy>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : empty ? (
        <Card>
          <EmptyState
            icon={<GitPullRequestArrow />}
            title="No tasks yet"
            description="Ask the agent to rename a symbol, fix a failing test or add a helper. It runs your tests before and after, and you review the diff."
            action={canCreate ? <Button onClick={() => setCreating(true)}>New task</Button> : null}
          />
        </Card>
      ) : tasks.data.items.length === 0 ? (
        <Card>
          <EmptyState title="No task matches" description="Change the filters to see more." />
        </Card>
      ) : (
        <>
          <Card className="overflow-hidden">
            <ul className="divide-border divide-y" aria-label="Tasks">
              {tasks.data.items.map((task) => (
                <li key={task.id}>
                  <Link
                    href={wsPath(slug, "tasks", String(task.number))}
                    className="hover:bg-muted flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 transition-colors"
                  >
                    <span className="text-subtle tabular w-10 shrink-0 text-[12.5px]">#{task.number}</span>
                    <span className="min-w-0 flex-1 basis-56">
                      <span className="block truncate text-[14px] font-medium">{task.title}</span>
                      <span className="text-muted-foreground block truncate text-[12.5px]">
                        {task.repository}
                        {task.requested_by ? ` / ${task.requested_by}` : ""}
                      </span>
                    </span>
                    {task.skill ? <Badge tone="outline">{SKILL_LABEL[task.skill] ?? task.skill}</Badge> : null}
                    {task.patch_count > 1 ? <Badge tone="neutral">{task.patch_count} revisions</Badge> : null}
                    <TaskStatusBadge status={task.status} />
                    <RelativeTime iso={task.updated_at} compact className="text-subtle w-10 text-right text-[12px]" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          {tasks.data.total > PAGE_SIZE ? (
            <Pagination
              className="mt-4"
              total={tasks.data.total}
              limit={PAGE_SIZE}
              offset={offset}
              onOffsetChange={(next) => update({ offset: next || null })}
              noun="tasks"
            />
          ) : null}
        </>
      )}
      <NewTaskDialog open={creating} onOpenChange={setCreating} />
    </PageBody>
  );
}

export function TasksView() {
  return (
    <Suspense>
      <TasksBody />
    </Suspense>
  );
}
