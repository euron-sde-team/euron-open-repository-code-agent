"use client";

import { FlaskConical, FolderGit2, GitPullRequestArrow, MessageSquareCode, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AreaTrend, BarTrend, DonutChart, SERIES } from "@/components/charts";
import { RelativeTime } from "@/components/domain/relative-time";
import { CaseStatusBadge, RunStatusBadge, TaskStatusBadge } from "@/components/domain/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { StatCard } from "@/components/ui/stat-card";
import { formatCompact, formatDay, formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { TASK_STATUS } from "@/lib/labels";
import { wsPath } from "@/lib/navigation";
import { useOverview } from "@/lib/queries";
import type { RunStatus, TaskStatus } from "@/lib/types";
import { useActiveWorkspace } from "@/lib/workspace-context";

const RANGES = [
  { value: "7", label: "7 days" },
  { value: "14", label: "14 days" },
  { value: "30", label: "30 days" },
] as const;

const STATUS_COLOR: Record<string, string> = {
  applied: "var(--success)",
  awaiting_review: "var(--warning)",
  approved: "var(--series-1)",
  running: "var(--info)",
  queued: "var(--series-6)",
  applying: "var(--info)",
  rejected: "var(--danger)",
  failed: "var(--danger)",
  cancelled: "var(--series-6)",
};

const KIND_ICON = { task: GitPullRequestArrow, test_run: FlaskConical } as const;

export function OverviewView() {
  const { slug, name } = useActiveWorkspace();
  const [range, setRange] = useState<(typeof RANGES)[number]["value"]>("14");
  const overview = useOverview(slug, Number(range));

  if (overview.error) {
    return <ErrorState message={overview.error.message} onRetry={() => overview.refetch()} className="py-24" />;
  }
  const data = overview.data;
  const totals = data?.totals;

  return (
    <PageBody>
      <PageHeader
        title="Overview"
        description={`What is happening in ${name}.`}
        actions={
          <SegmentedControl
            label="Time range"
            value={range}
            onValueChange={setRange}
            options={RANGES.map((r) => ({ value: r.value, label: r.label }))}
          />
        }
      />
      {!data || !totals ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Repositories"
              value={formatNumber(totals.repositories)}
              icon={<FolderGit2 />}
              caption={`${formatCompact(totals.files)} files, ${formatCompact(totals.symbols)} symbols, ${formatCompact(totals.lines)} lines`}
            />
            <Link href={`${wsPath(slug, "tasks")}?status=awaiting_review`} className="block rounded-xl">
              <StatCard
                label="Awaiting review"
                value={formatNumber(totals.open_reviews)}
                icon={<GitPullRequestArrow />}
                caption={
                  totals.tasks > 0
                    ? `${formatNumber(totals.tasks)} tasks, ${formatPercent(totals.approval_rate)} of reviews approved`
                    : "No tasks in this period"
                }
                className="hover:border-input h-full transition-colors"
              />
            </Link>
            <Link href={wsPath(slug, "runs")} className="block rounded-xl">
              <StatCard
                label="Test pass rate"
                value={totals.test_runs ? formatPercent(totals.test_pass_rate) : "None"}
                icon={<FlaskConical />}
                caption={
                  totals.test_runs
                    ? `${formatNumber(totals.test_runs)} runs, median ${formatDuration(totals.median_run_ms)}`
                    : "No runs in this period"
                }
                className="hover:border-input h-full transition-colors"
              />
            </Link>
            <StatCard
              label="Questions and searches"
              value={formatNumber(totals.questions + totals.searches)}
              icon={<MessageSquareCode />}
              caption={`${formatNumber(totals.questions)} questions, ${formatNumber(totals.searches)} searches`}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Test runs per day</CardTitle>
              </CardHeader>
              <CardContent>
                <BarTrend
                  label="Test runs per day, passed and failed"
                  data={data.daily}
                  xKey="day"
                  xFormat={formatDay}
                  stacked
                  height={220}
                  series={[
                    { key: "runs_passed", name: "Passed", color: "var(--success)" },
                    { key: "runs_failed", name: "Failed", color: "var(--danger)" },
                  ]}
                />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Questions and searches per day</CardTitle>
              </CardHeader>
              <CardContent>
                <AreaTrend
                  label="Questions asked and searches run per day"
                  data={data.daily}
                  xKey="day"
                  xFormat={formatDay}
                  height={220}
                  series={[
                    { key: "questions", name: "Questions", color: SERIES[0] },
                    { key: "searches", name: "Searches", color: SERIES[1] },
                  ]}
                />
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Card>
              <CardHeader>
                <CardTitle>Tasks by outcome</CardTitle>
              </CardHeader>
              <CardContent>
                {data.tasks_by_status.length === 0 ? (
                  <EmptyState
                    title="No tasks yet"
                    description="Describe a change on the Tasks page."
                    className="py-8"
                  />
                ) : (
                  <DonutChart
                    label="Tasks by status"
                    centerValue={formatNumber(totals.tasks)}
                    centerLabel="tasks"
                    slices={data.tasks_by_status.map((s) => ({
                      name: TASK_STATUS[s.status as TaskStatus]?.label ?? s.status,
                      value: s.count,
                      color: STATUS_COLOR[s.status] ?? "var(--series-6)",
                    }))}
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Recent work</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.recent.length === 0 ? (
                  <EmptyState title="Nothing yet" className="py-8" />
                ) : (
                  <ul className="divide-border divide-y">
                    {data.recent.slice(0, 7).map((item) => {
                      const Icon = KIND_ICON[item.kind as keyof typeof KIND_ICON] ?? Search;
                      return (
                        <li key={`${item.kind}-${item.href}`}>
                          <Link
                            href={item.href}
                            className="hover:bg-muted flex items-center gap-3 px-5 py-2.5 transition-colors"
                          >
                            <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
                              <Icon className="size-4" aria-hidden />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-[13.5px] font-medium">{item.title}</span>
                              <span className="text-muted-foreground block truncate text-[12px]">
                                {item.detail}
                                {item.actor ? ` by ${item.actor}` : ""}
                              </span>
                            </span>
                            {item.kind === "task" ? (
                              <TaskStatusBadge status={item.status as TaskStatus} />
                            ) : item.kind === "test_run" ? (
                              <RunStatusBadge status={item.status as RunStatus} />
                            ) : (
                              <CaseStatusBadge status={item.status} />
                            )}
                            <RelativeTime iso={item.at} compact className="text-subtle w-9 text-right text-[12px]" />
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </PageBody>
  );
}
