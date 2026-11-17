"use client";

import { FileQuestion, ListTree, PanelRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { CodeView } from "@/components/code/code-view";
import { FileTree } from "@/components/code/file-tree";
import { SymbolPanel } from "@/components/code/symbol-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatBytes, formatNumber } from "@/lib/format";
import { symbolAt } from "@/lib/lines";
import { codePath, parseLineHash, wsPath } from "@/lib/navigation";
import { useBlob, useFiles, useRepository } from "@/lib/queries";
import type { Blob, OutlineSymbol } from "@/lib/types";
import { replaceHash, useHash } from "@/lib/use-hash";
import { useActiveWorkspace } from "@/lib/workspace-context";

function Outline({
  outline,
  activeId,
  onPick,
}: {
  outline: OutlineSymbol[];
  activeId: string | null;
  onPick: (symbol: OutlineSymbol) => void;
}) {
  if (outline.length === 0) {
    return <p className="text-muted-foreground px-1 py-3 text-[13px]">No symbols were extracted from this file.</p>;
  }
  return (
    <ul>
      {outline.map((symbol) => (
        <li key={symbol.id}>
          <button
            type="button"
            onClick={() => onPick(symbol)}
            aria-current={symbol.id === activeId ? "true" : undefined}
            style={{ paddingLeft: `${symbol.depth * 14 + 8}px` }}
            className={cn(
              "flex w-full items-baseline gap-2 rounded-md py-1 pr-2 text-left text-[12.5px] transition-colors",
              symbol.id === activeId ? "bg-accent text-accent-foreground" : "hover:bg-muted",
            )}
          >
            <span className="text-subtle w-14 shrink-0 text-[10.5px] tracking-wide uppercase">{symbol.kind}</span>
            <span className="min-w-0 truncate font-mono">{symbol.name}</span>
            <span className="text-subtle tabular ml-auto shrink-0 text-[11px]">{symbol.start_line}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function FileHeader({ blob, repo, workspace }: { blob: Blob; repo: string; workspace: string }) {
  const parts = blob.path.split("/");
  return (
    <div className="border-border bg-card flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2.5">
      <nav aria-label="File path" className="min-w-0 flex-1 truncate font-mono text-[12.5px]">
        <Link
          href={wsPath(workspace, "repos", encodeURIComponent(repo), "code")}
          className="text-muted-foreground hover:text-foreground"
        >
          {repo}
        </Link>
        {parts.map((part, index) => (
          <span key={`${part}-${index}`}>
            <span className="text-subtle"> / </span>
            <span className={index === parts.length - 1 ? "text-foreground font-semibold" : "text-muted-foreground"}>
              {part}
            </span>
          </span>
        ))}
      </nav>
      <div className="flex shrink-0 items-center gap-2 text-[12px]">
        <Badge tone="outline">{blob.language}</Badge>
        {blob.is_test ? <Badge tone="info">test file</Badge> : null}
        <span className="text-muted-foreground tabular">
          {formatNumber(blob.line_count)} lines, {formatBytes(blob.size_bytes)}
        </span>
      </div>
    </div>
  );
}

function FileBody({ repo, path }: { repo: string; path: string }) {
  const { slug } = useActiveWorkspace();
  const blob = useBlob(slug, repo, path);
  const hash = useHash();
  const [symbolId, setSymbolId] = useState<{ path: string; id: string } | null>(null);
  const [panel, setPanel] = useState(false);

  if (blob.error) {
    const missing = blob.error instanceof ApiError && blob.error.status === 404;
    return missing ? (
      <EmptyState
        icon={<FileQuestion />}
        title="File not found"
        description={`${path} is not in the indexed snapshot of this repository.`}
        className="py-24"
      />
    ) : (
      <ErrorState message={blob.error.message} onRetry={() => blob.refetch()} />
    );
  }
  const data = blob.data;
  if (!data) {
    return (
      <div className="space-y-2 p-6" aria-busy>
        <Skeleton className="h-5 w-72" />
        <Skeleton className="h-96" />
      </div>
    );
  }
  const range = parseLineHash(hash);
  // The symbol panel follows the selected lines unless one was picked from the outline.
  const picked = symbolId && symbolId.path === path ? symbolId.id : null;
  const fromRange = range ? (symbolAt(data.outline, range.start)?.id ?? null) : null;
  const activeId = picked ?? fromRange;

  const pick = (symbol: OutlineSymbol) => {
    setSymbolId({ path, id: symbol.id });
    replaceHash(`#L${symbol.start_line}-L${symbol.end_line}`);
  };

  const side = (
    <Tabs defaultValue="outline" className="flex h-full min-h-0 flex-col">
      <TabsList>
        <TabsTrigger value="outline">Outline</TabsTrigger>
        <TabsTrigger value="symbol">Symbol</TabsTrigger>
      </TabsList>
      <TabsContent value="outline" className="scroll-quiet min-h-0 flex-1 overflow-y-auto pt-3">
        <Outline outline={data.outline} activeId={activeId} onPick={pick} />
      </TabsContent>
      <TabsContent value="symbol" className="scroll-quiet min-h-0 flex-1 overflow-y-auto pt-3">
        <SymbolPanel workspace={slug} repo={repo} symbolId={activeId} />
      </TabsContent>
    </Tabs>
  );

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <FileHeader blob={data} repo={repo} workspace={slug} />
        {data.parse_error ? (
          <p className="bg-warning-soft text-warning px-4 py-2 text-[12.5px]">
            This file could not be fully parsed, so its symbols may be missing: {data.parse_error}
          </p>
        ) : null}
        <div className="scroll-quiet min-h-0 flex-1 overflow-auto">
          {data.indexed ? (
            <CodeView lines={data.lines} hash={hash} file={path} />
          ) : (
            <EmptyState
              title="Not indexed"
              description="This file is binary or larger than the per-file limit, so its content is not stored."
              className="py-24"
            />
          )}
        </div>
      </div>
      <aside className="border-border bg-card hidden w-80 shrink-0 border-l p-3 xl:block" aria-label="Symbols">
        {side}
      </aside>
      <Button
        variant="secondary"
        size="icon"
        aria-label="Show symbols"
        className="fixed right-4 bottom-4 z-20 shadow-md xl:hidden"
        onClick={() => setPanel(true)}
      >
        <PanelRight />
      </Button>
      <Sheet open={panel} onOpenChange={setPanel}>
        <SheetContent side="right" title="Symbols" className="w-[min(92vw,22rem)] p-3 pt-12">
          {side}
        </SheetContent>
      </Sheet>
    </div>
  );
}

/** The two- or three-pane code view: the file tree, a file with anchors, its symbols. */
export function CodeBrowser({ repo, path }: { repo: string; path: string | null }) {
  const { slug } = useActiveWorkspace();
  const repository = useRepository(slug, repo);
  const indexed = Boolean(repository.data?.current_snapshot);
  const files = useFiles(slug, repo, indexed);
  const [tree, setTree] = useState(false);

  if (repository.error)
    return <ErrorState message={repository.error.message} onRetry={() => repository.refetch()} className="py-24" />;
  if (repository.data && !indexed) {
    return (
      <EmptyState
        title="Nothing to browse yet"
        description="This repository has no finished index. Come back when indexing is done."
        action={
          <Button asChild variant="secondary">
            <Link href={wsPath(slug, "repos", encodeURIComponent(repo))}>Back to the repository</Link>
          </Button>
        }
        className="py-24"
      />
    );
  }

  const treeNode = files.data ? (
    <FileTree files={files.data.files} current={path} workspace={slug} repo={repo} />
  ) : (
    <div className="space-y-2" aria-busy>
      <Skeleton className="h-8" />
      <Skeleton className="h-40" />
    </div>
  );

  return (
    <div className="flex h-full min-h-0">
      <aside
        className="border-border bg-sidebar hidden w-72 shrink-0 border-r p-3 lg:block"
        aria-label="Repository files"
      >
        {treeNode}
      </aside>
      <Sheet open={tree} onOpenChange={setTree}>
        <SheetContent side="left" title="Files" className="w-[min(88vw,20rem)] p-3 pt-12">
          {treeNode}
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-border flex items-center gap-2 border-b px-3 py-1.5 lg:hidden">
          <Button variant="secondary" size="sm" onClick={() => setTree(true)}>
            <ListTree /> Files
          </Button>
          <span className="text-muted-foreground truncate font-mono text-[12px]">{path ?? repo}</span>
        </div>
        {path ? (
          <FileBody repo={repo} path={path} key={`${repo}:${path}`} />
        ) : (
          <EmptyState
            icon={<ListTree />}
            title="Choose a file"
            description={
              files.data
                ? `${formatNumber(files.data.files.length)} files are indexed. Pick one on the left, or open a symbol from search.`
                : "Loading the file list."
            }
            action={
              files.data?.files[0] ? (
                <Button asChild variant="secondary" size="sm">
                  <Link
                    href={codePath(
                      slug,
                      repo,
                      files.data.files.find((f) => f.indexed)?.path ?? files.data.files[0].path,
                    )}
                  >
                    Open the first file
                  </Link>
                </Button>
              ) : null
            }
            className="py-24"
          />
        )}
      </div>
    </div>
  );
}
