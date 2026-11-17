"use client";

import { Code2, FlaskConical, RefreshCw, Settings2, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { RelativeTime } from "@/components/domain/relative-time";
import { Markdown } from "@/components/domain/markdown";
import { LanguageBar } from "@/components/domain/language-bar";
import { IndexStatusBadge, RunStatusBadge, TaskStatusBadge } from "@/components/domain/status-badge";
import { RepoSettingsDialog } from "@/components/repos/repo-settings-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState, ErrorNotice, ErrorState, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { StatCard } from "@/components/ui/stat-card";
import { formatBytes, formatCompact, formatDuration, formatNumber } from "@/lib/format";
import { RUN_TRIGGER } from "@/lib/labels";
import { wsPath } from "@/lib/navigation";
import {
  useBlob,
  useDeleteRepository,
  useRepository,
  useRuns,
  useStartRun,
  useSyncRepository,
  useTasks,
  useUploadVersion,
} from "@/lib/queries";
import type { RepositoryDetail } from "@/lib/types";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";

function Readme({ workspace, repo, path }: { workspace: string; repo: string; path: string }) {
  const blob = useBlob(workspace, repo, path);
  if (blob.isLoading) return <Skeleton className="h-40" />;
  if (!blob.data) return null;
  const text = blob.data.lines.map((line) => line.map(([, t]) => t).join("")).join("\n");
  return <Markdown text={text} />;
}

function Snapshots({ repository }: { repository: RepositoryDetail }) {
  const current = repository.current_snapshot;
  const latest = repository.latest_snapshot;
  const snapshots = [latest, current].filter((s, i, all) => s && all.findIndex((o) => o?.id === s.id) === i);
  if (snapshots.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Index</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3 text-[13px]">
          {snapshots.map((snapshot) =>
            snapshot ? (
              <li key={snapshot.id} className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">
                    {snapshot.id === current?.id ? "Current snapshot" : "Latest attempt"}
                  </span>
                  <IndexStatusBadge status={snapshot.status} />
                </div>
                <p className="text-muted-foreground text-[12.5px]">
                  {snapshot.origin === "upload"
                    ? `Uploaded ${snapshot.upload_name ?? "archive"}`
                    : snapshot.origin === "sync"
                      ? "Synced"
                      : "Cloned"}
                  {snapshot.commit_sha ? (
                    <>
                      {" at "}
                      <code className="bg-muted rounded px-1 font-mono text-[11.5px]">
                        {snapshot.commit_sha.slice(0, 8)}
                      </code>
                    </>
                  ) : null}{" "}
                  <RelativeTime iso={snapshot.indexed_at ?? snapshot.created_at} />
                </p>
                {snapshot.error ? <p className="text-danger text-[12.5px]">{snapshot.error}</p> : null}
                {snapshot.warnings.length > 0 ? (
                  <p className="text-warning text-[12.5px]">
                    {snapshot.warnings.length} file{snapshot.warnings.length === 1 ? "" : "s"} could not be fully
                    indexed.
                  </p>
                ) : null}
              </li>
            ) : null,
          )}
        </ul>
      </CardContent>
    </Card>
  );
}

function Related({ workspace, repo }: { workspace: string; repo: string }) {
  const tasks = useTasks(workspace, { repository: repo, limit: 5 });
  const runs = useRuns(workspace, { repository: repo, limit: 5 });
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Recent tasks</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {tasks.data && tasks.data.items.length === 0 ? (
            <EmptyState
              title="No tasks yet"
              description="Describe a change and the agent proposes a patch."
              className="py-8"
            />
          ) : (
            <ul className="divide-border divide-y">
              {tasks.data?.items.map((task) => (
                <li key={task.id}>
                  <Link
                    href={wsPath(workspace, "tasks", String(task.number))}
                    className="hover:bg-muted flex items-center gap-3 px-5 py-2.5"
                  >
                    <span className="text-subtle tabular w-8 text-[12px]">#{task.number}</span>
                    <span className="min-w-0 flex-1 truncate text-[13.5px]">{task.title}</span>
                    <TaskStatusBadge status={task.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recent test runs</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {runs.data && runs.data.items.length === 0 ? (
            <EmptyState title="No runs yet" description="Run the tests in the sandbox." className="py-8" />
          ) : (
            <ul className="divide-border divide-y">
              {runs.data?.items.map((run) => (
                <li key={run.id}>
                  <Link
                    href={wsPath(workspace, "runs", String(run.number))}
                    className="hover:bg-muted flex items-center gap-3 px-5 py-2.5"
                  >
                    <span className="text-subtle tabular w-8 text-[12px]">#{run.number}</span>
                    <span className="min-w-0 flex-1 truncate text-[13.5px]">
                      {RUN_TRIGGER[run.trigger] ?? run.trigger}
                      <span className="text-muted-foreground text-[12px]">
                        {run.total ? `, ${run.passed}/${run.total} passed` : ""}
                        {run.duration_ms ? `, ${formatDuration(run.duration_ms)}` : ""}
                      </span>
                    </span>
                    <RunStatusBadge status={run.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function RepoDetail({ repo }: { repo: string }) {
  const { slug } = useActiveWorkspace();
  const router = useRouter();
  const canManage = useCan("maintainer");
  const canRun = useCan("developer");
  const repository = useRepository(slug, repo);
  const sync = useSyncRepository(slug, repo);
  const upload = useUploadVersion(slug, repo);
  const start = useStartRun(slug);
  const remove = useDeleteRepository(slug, repo);
  const [settings, setSettings] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  if (repository.error) {
    return <ErrorState message={repository.error.message} onRetry={() => repository.refetch()} className="py-24" />;
  }
  const data = repository.data;
  if (!data) {
    return (
      <PageBody>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-6 h-96" />
      </PageBody>
    );
  }
  const busy =
    data.status === "queued" ||
    data.status === "indexing" ||
    data.latest_snapshot?.status === "queued" ||
    data.latest_snapshot?.status === "indexing";
  const canTest = canRun && data.settings.test_command && data.current_snapshot;

  return (
    <PageBody>
      <PageHeader
        title={data.name}
        documentTitle={`${data.name} (repository)`}
        breadcrumbs={[{ label: "Repositories", href: wsPath(slug, "repos") }, { label: data.name }]}
        description={data.description || (data.git_url ?? "Uploaded archive")}
        actions={
          <>
            <IndexStatusBadge status={data.status} />
            {data.current_snapshot ? (
              <Button asChild variant="secondary" size="sm">
                <Link href={wsPath(slug, "repos", encodeURIComponent(data.slug), "code")}>
                  <Code2 /> Browse code
                </Link>
              </Button>
            ) : null}
            {canTest ? (
              <Button
                variant="secondary"
                size="sm"
                loading={start.isPending}
                onClick={async () => {
                  const run = await start.mutateAsync(data.slug);
                  toast.success(`Test run #${run.number} queued`);
                  router.push(wsPath(slug, "runs", String(run.number)));
                }}
              >
                <FlaskConical /> Run tests
              </Button>
            ) : null}
            {canManage ? (
              <>
                {data.source === "git" ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    loading={sync.isPending}
                    onClick={async () => {
                      await sync.mutateAsync();
                      toast.success("Sync started");
                    }}
                  >
                    <RefreshCw /> Sync
                  </Button>
                ) : (
                  <>
                    <input
                      ref={fileInput}
                      type="file"
                      accept=".zip,.tar,.tar.gz,.tgz"
                      className="sr-only"
                      aria-label="Upload a new version of the archive"
                      tabIndex={-1}
                      onChange={async (event) => {
                        const file = event.target.files?.[0];
                        event.target.value = "";
                        if (!file) return;
                        await upload.mutateAsync(file);
                        toast.success("New version uploaded, indexing");
                      }}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busy}
                      loading={upload.isPending}
                      onClick={() => fileInput.current?.click()}
                    >
                      <Upload /> Upload new version
                    </Button>
                  </>
                )}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Repository settings"
                  onClick={() => setSettings(true)}
                >
                  <Settings2 />
                </Button>
                <Button
                  variant="danger-ghost"
                  size="icon-sm"
                  aria-label="Delete repository"
                  onClick={() => setDeleting(true)}
                >
                  <Trash2 />
                </Button>
              </>
            ) : null}
          </>
        }
      />

      {data.status === "failed" && data.error ? (
        <ErrorNotice message={`Indexing failed: ${data.error}`} className="mb-4" />
      ) : null}
      {busy ? (
        <p className="text-muted-foreground bg-info-soft mb-4 rounded-lg px-3 py-2 text-[13px]" role="status">
          <span className="text-info font-medium">Indexing.</span> Files, symbols and call relationships appear when it
          finishes.
        </p>
      ) : null}

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Files"
          value={formatNumber(data.file_count)}
          caption={`${formatBytes(data.size_bytes)} indexed`}
        />
        <StatCard
          label="Symbols"
          value={formatCompact(data.symbol_count)}
          caption="Classes, functions, methods, constants"
        />
        <StatCard
          label="Lines of code"
          value={formatCompact(data.line_count)}
          caption={`${Object.keys(data.languages).length} languages`}
        />
        <StatCard
          label="Last indexed"
          value={data.last_indexed_at ? <RelativeTime iso={data.last_indexed_at} /> : "Never"}
          caption={
            data.current_snapshot?.commit_sha
              ? `Commit ${data.current_snapshot.commit_sha.slice(0, 8)}`
              : data.source === "git"
                ? (data.default_branch ?? "Default branch")
                : "Uploaded archive"
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{data.readme_path ?? "README"}</CardTitle>
          </CardHeader>
          <CardContent>
            {data.readme_path ? (
              <Readme workspace={slug} repo={data.slug} path={data.readme_path} />
            ) : (
              <p className="text-muted-foreground text-[13px]">This repository has no README at its root.</p>
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Languages</CardTitle>
            </CardHeader>
            <CardContent>
              {data.file_count > 0 ? (
                <LanguageBar languages={data.languages} max={6} />
              ) : (
                <p className="text-muted-foreground text-[13px]">Not indexed yet.</p>
              )}
            </CardContent>
          </Card>
          <Snapshots repository={data} />
          <Card>
            <CardHeader>
              <CardTitle>Tests</CardTitle>
            </CardHeader>
            <CardContent className="text-[13px]">
              {data.settings.test_command ? (
                <code
                  tabIndex={0}
                  className="bg-code border-border block overflow-x-auto rounded-lg border px-3 py-2 font-mono text-[12.5px]"
                >
                  {data.settings.test_command}
                </code>
              ) : (
                <p className="text-muted-foreground">Test runs are disabled for this repository.</p>
              )}
              <p className="text-muted-foreground mt-2 text-[12px]">
                Runs in a sandbox with no network and capped CPU, memory and time.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="mt-4">
        <Related workspace={slug} repo={data.slug} />
      </div>

      {settings ? <RepoSettingsDialog workspace={slug} repository={data} open onOpenChange={setSettings} /> : null}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${data.name}?`}
        description="Its index, tasks, patches and test runs are deleted with it. This cannot be undone."
        confirmLabel="Delete repository"
        destructive
        onConfirm={async () => {
          await remove.mutateAsync();
          toast.success(`${data.name} deleted`);
          router.replace(wsPath(slug, "repos"));
        }}
      />
    </PageBody>
  );
}
