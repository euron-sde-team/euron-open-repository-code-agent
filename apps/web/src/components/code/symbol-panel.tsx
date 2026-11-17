"use client";

import { ArrowDownLeft, ArrowUpRight, FlaskConical } from "lucide-react";
import Link from "next/link";

import { CodeSnippet } from "@/components/domain/code-lines";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { codePath } from "@/lib/navigation";
import { useSymbol } from "@/lib/queries";
import type { Edge } from "@/lib/types";

function EdgeList({
  title,
  icon,
  edges,
  workspace,
  repo,
  empty,
}: {
  title: string;
  icon: React.ReactNode;
  edges: Edge[];
  workspace: string;
  repo: string;
  empty: string;
}) {
  return (
    <section aria-label={title}>
      <h4 className="text-muted-foreground mb-1.5 flex items-center gap-1.5 text-[11.5px] font-medium tracking-wider uppercase [&_svg]:size-3.5">
        {icon} {title} <span className="tabular">({edges.length})</span>
      </h4>
      {edges.length === 0 ? (
        <p className="text-muted-foreground text-[12.5px]">{empty}</p>
      ) : (
        <ul className="space-y-0.5">
          {edges.slice(0, 12).map((edge, index) => (
            <li key={`${edge.path}:${edge.line}:${index}`}>
              <Link
                href={codePath(workspace, repo, edge.path, edge.line)}
                className="hover:bg-muted flex items-baseline gap-2 rounded-md px-1.5 py-1 text-[12.5px]"
              >
                <span className="min-w-0 truncate font-mono text-[12px]">{edge.name}</span>
                <span className="text-subtle ml-auto shrink-0 truncate font-mono text-[11.5px]">
                  {edge.path}:{edge.line}
                </span>
              </Link>
            </li>
          ))}
          {edges.length > 12 ? <li className="text-subtle px-1.5 text-[12px]">and {edges.length - 12} more</li> : null}
        </ul>
      )}
    </section>
  );
}

/** What the index knows about one symbol: its code, who calls it, what it calls, its tests. */
export function SymbolPanel({
  workspace,
  repo,
  symbolId,
}: {
  workspace: string;
  repo: string;
  symbolId: string | null;
}) {
  const symbol = useSymbol(workspace, symbolId);
  if (!symbolId) {
    return (
      <EmptyState
        title="Pick a symbol"
        description="Choose one from the outline to see its callers, callees and tests."
        className="py-10"
      />
    );
  }
  if (symbol.error) return <ErrorState message={symbol.error.message} onRetry={() => symbol.refetch()} />;
  const data = symbol.data;
  if (!data) {
    return (
      <div className="space-y-3 p-1" aria-busy>
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-24" />
        <Skeleton className="h-16" />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="primary">{data.kind}</Badge>
          <span className="text-muted-foreground tabular text-[12px]">{data.ref_count} references</span>
        </div>
        <h3 className="mt-1.5 font-mono text-[13.5px] font-semibold break-all">{data.qualified_name}</h3>
        {data.doc ? <p className="text-muted-foreground mt-1 text-[13px]">{data.doc}</p> : null}
      </div>
      <CodeSnippet lines={data.code.slice(0, 18)} firstLine={data.start_line} />
      {data.code.length > 18 ? (
        <p className="text-subtle -mt-2 text-[12px]">First 18 of {data.code.length} lines.</p>
      ) : null}
      <EdgeList
        title="Called by"
        icon={<ArrowDownLeft />}
        edges={data.callers}
        workspace={workspace}
        repo={repo}
        empty="Nothing in the index calls it."
      />
      <EdgeList
        title="Calls"
        icon={<ArrowUpRight />}
        edges={data.callees}
        workspace={workspace}
        repo={repo}
        empty="It calls nothing the index can resolve."
      />
      <EdgeList
        title="Tests"
        icon={<FlaskConical />}
        edges={data.tests}
        workspace={workspace}
        repo={repo}
        empty="No test references it directly."
      />
    </div>
  );
}
