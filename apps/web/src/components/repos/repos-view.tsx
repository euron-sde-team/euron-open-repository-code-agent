"use client";

import { Archive, FileCode2, FolderGit2, GitBranch, Plus } from "lucide-react";
import Link from "next/link";
import { Suspense, useState } from "react";

import { IndexStatusBadge } from "@/components/domain/status-badge";
import { LanguageBar } from "@/components/domain/language-bar";
import { RelativeTime } from "@/components/domain/relative-time";
import { ConnectDialog } from "@/components/repos/connect-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { FilterBar, SearchField } from "@/components/ui/filter-bar";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Pagination } from "@/components/ui/pagination";
import { formatCompact } from "@/lib/format";
import { wsPath } from "@/lib/navigation";
import { useRepositories } from "@/lib/queries";
import type { Repository } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";

const PAGE_SIZE = 12;

function RepoCard({ repository, workspace }: { repository: Repository; workspace: string }) {
  const SourceIcon = repository.source === "git" ? GitBranch : Archive;
  return (
    <Card className="hover:border-input relative flex flex-col gap-3 p-4 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold tracking-tight">
            <Link
              href={wsPath(workspace, "repos", encodeURIComponent(repository.slug))}
              className="after:absolute after:inset-0 after:content-['']"
            >
              {repository.name}
            </Link>
          </h2>
          <p className="text-muted-foreground mt-0.5 line-clamp-2 min-h-[2.4em] text-[13px]">
            {repository.description || "No description."}
          </p>
        </div>
        <IndexStatusBadge status={repository.status} />
      </div>
      {repository.status === "failed" && repository.error ? (
        <p className="text-danger text-[12.5px]">{repository.error}</p>
      ) : repository.file_count > 0 ? (
        <LanguageBar languages={repository.languages} />
      ) : (
        <p className="text-muted-foreground text-[12.5px]">Waiting for the first index.</p>
      )}
      <dl className="text-muted-foreground mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
        <div className="flex items-center gap-1.5">
          <dt className="sr-only">Files</dt>
          <FileCode2 className="size-3.5" aria-hidden />
          <dd className="tabular">{formatCompact(repository.file_count)} files</dd>
        </div>
        <div className="flex items-center gap-1.5">
          <dt className="sr-only">Symbols</dt>
          <dd className="tabular">{formatCompact(repository.symbol_count)} symbols</dd>
        </div>
        <div className="flex items-center gap-1.5">
          <dt className="sr-only">Source</dt>
          <SourceIcon className="size-3.5" aria-hidden />
          <dd>{repository.source === "git" ? "Git" : "Archive"}</dd>
        </div>
        <div className="ml-auto">
          <dt className="sr-only">Last indexed</dt>
          <dd>
            <RelativeTime iso={repository.last_indexed_at} />
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function ReposBody() {
  const { slug } = useActiveWorkspace();
  const canConnect = useCan("maintainer");
  const { get, update } = useUrlParams();
  const [connecting, setConnecting] = useState(false);
  const [text, setText] = useState(get("q") ?? "");
  const q = useDebouncedValue(text, 250);
  const offset = Number(get("offset") ?? 0) || 0;
  const repositories = useRepositories(slug, { q: q || undefined, limit: PAGE_SIZE, offset });

  const items = repositories.data?.items ?? [];
  const empty = repositories.data && repositories.data.total === 0 && !q;
  return (
    <PageBody>
      <PageHeader
        title="Repositories"
        description="Indexed code your team can search, ask about and change with review."
        actions={
          canConnect ? (
            <Button onClick={() => setConnecting(true)}>
              <Plus /> Connect repository
            </Button>
          ) : null
        }
      />
      {empty ? null : (
        <FilterBar className="mb-4">
          <SearchField
            value={text}
            onChange={(value) => {
              setText(value);
              update({ offset: null });
            }}
            label="Search repositories"
          />
        </FilterBar>
      )}
      {repositories.error ? (
        <ErrorState message={repositories.error.message} onRetry={() => repositories.refetch()} />
      ) : !repositories.data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-busy>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : empty ? (
        <Card>
          <EmptyState
            icon={<FolderGit2 />}
            title="Connect your first repository"
            description={
              canConnect
                ? "Upload an archive or give a git URL. CodeAgent indexes files, symbols and call relationships, then you can search and ask."
                : "A maintainer connects repositories. Ask one to add yours."
            }
            action={canConnect ? <Button onClick={() => setConnecting(true)}>Connect repository</Button> : null}
          />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState title="No repository matches" description={`Nothing is named like "${q}".`} />
        </Card>
      ) : (
        <>
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((repository) => (
              <li key={repository.id} className="contents">
                <RepoCard repository={repository} workspace={slug} />
              </li>
            ))}
          </ul>
          {repositories.data.total > PAGE_SIZE ? (
            <Pagination
              className="mt-5"
              total={repositories.data.total}
              limit={PAGE_SIZE}
              offset={offset}
              onOffsetChange={(next) => update({ offset: next || null })}
              noun="repositories"
            />
          ) : null}
        </>
      )}
      <ConnectDialog open={connecting} onOpenChange={setConnecting} />
    </PageBody>
  );
}

export function ReposView() {
  return (
    <Suspense>
      <ReposBody />
    </Suspense>
  );
}
