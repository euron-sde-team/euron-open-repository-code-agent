"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Wordmark } from "@/components/brand";
import { isNavActive, NAV_GROUPS } from "@/components/shell/nav";
import { ThemeMenu } from "@/components/shell/theme-menu";
import { UserMenu } from "@/components/shell/user-menu";
import { WorkspaceSwitcher } from "@/components/shell/workspace-switcher";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui/feedback";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { wsPath } from "@/lib/navigation";
import { useMe, useWorkspace } from "@/lib/queries";
import { runtimeEnv } from "@/lib/runtime-env";
import { LAST_WORKSPACE_KEY, writeLocal } from "@/lib/storage";
import type { Me, WorkspaceSummary } from "@/lib/types";
import { WorkspaceProvider } from "@/lib/workspace-context";

function Sidebar({ me, current, onNavigate }: { me: Me; current: WorkspaceSummary; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <div className="border-sidebar-border bg-sidebar flex h-full w-64 flex-col border-r">
      <div className="px-3 pt-3 pb-2">
        <WorkspaceSwitcher current={current} all={me.workspaces} />
      </div>
      <nav className="scroll-quiet mt-1 min-h-0 flex-1 overflow-y-auto px-3 pb-3" aria-label="Workspace">
        {NAV_GROUPS.map((group, index) => (
          <div key={group.label ?? index} className={cn(index > 0 && "mt-4")}>
            {group.label ? (
              <p className="text-subtle px-2.5 pb-1 text-[11px] font-medium tracking-wider uppercase">{group.label}</p>
            ) : null}
            <ul className="space-y-0.5">
              {group.items.map(({ segment, label, icon: Icon }) => {
                const active = isNavActive(pathname, current.slug, segment);
                return (
                  <li key={label}>
                    <Link
                      href={wsPath(current.slug, segment)}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13.5px] transition-colors [&_svg]:size-4",
                        active
                          ? "bg-card text-foreground ring-border font-medium shadow-sm ring-1"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <Icon className={active ? "text-primary" : ""} aria-hidden />
                      {label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-sidebar-border border-t p-3">
        <UserMenu account={me.user} workspace={current.slug} />
      </div>
    </div>
  );
}

function ContentSkeleton() {
  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 px-4 py-8 sm:px-6 lg:px-10" aria-busy>
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-80 max-w-full" />
      <div className="grid gap-4 pt-4 sm:grid-cols-2 lg:grid-cols-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}

/**
 * The frame of every page under /w/[workspace]: sidebar (a drawer on phones), workspace
 * switcher, user menu. It loads the signed-in person and the workspace first and renders the
 * page inside a WorkspaceProvider, so pages can call `useActiveWorkspace()` and `useCan()`
 * without loading states of their own.
 */
export function AppShell({ workspace, children }: { workspace: string; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useMe();
  // The path the drawer was opened on: navigating elsewhere closes it without an effect.
  const [drawerPath, setDrawerPath] = useState<string | null>(null);
  const drawer = drawerPath === pathname;
  // A refetch after signing in still carries the old 401 until it answers: wait for it.
  const unauthorized = me.error instanceof ApiError && me.error.status === 401 && !me.isFetching;
  const summary = me.data?.workspaces.find((w) => w.slug === workspace || w.id === workspace);
  const details = useWorkspace(summary?.slug ?? "", Boolean(summary));

  useEffect(() => {
    if (unauthorized) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [unauthorized, pathname, router]);

  useEffect(() => {
    if (summary) writeLocal(LAST_WORKSPACE_KEY, summary.slug);
  }, [summary]);

  if (me.isLoading || (me.isFetching && !me.data) || unauthorized) {
    return (
      <div className="flex h-dvh items-center justify-center" role="status" aria-label="Loading">
        <Spinner className="size-5" />
      </div>
    );
  }
  if (me.error || !me.data) {
    return (
      <ErrorState
        className="h-dvh"
        title="CodeAgent is unreachable"
        message={me.error?.message ?? "Try again shortly."}
        onRetry={() => me.refetch()}
      />
    );
  }
  if (!summary) {
    return (
      <EmptyState
        className="h-dvh"
        title="Workspace not found"
        description="It does not exist, or you are not a member of it."
        action={
          <Button asChild variant="secondary">
            <Link href="/">Go to my workspaces</Link>
          </Button>
        }
      />
    );
  }

  let content: ReactNode;
  if (details.data) {
    content = (
      <WorkspaceProvider workspace={details.data} summary={summary} me={me.data}>
        {children}
      </WorkspaceProvider>
    );
  } else if (details.error) {
    content = <ErrorState message={details.error.message} onRetry={() => details.refetch()} className="py-24" />;
  } else {
    content = <ContentSkeleton />;
  }

  return (
    <div className="flex h-dvh overflow-hidden">
      <a
        href="#main"
        className="bg-card text-foreground ring-ring sr-only z-50 rounded-lg px-3 py-2 text-sm font-medium shadow-md ring-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <aside className="hidden shrink-0 lg:block">
        <Sidebar me={me.data} current={summary} />
      </aside>
      <Sheet open={drawer} onOpenChange={(open) => setDrawerPath(open ? pathname : null)}>
        <SheetContent side="left" title="Navigation" hideTitle showClose={false} className="w-64 border-x-0 p-0">
          <Sidebar me={me.data} current={summary} onNavigate={() => setDrawerPath(null)} />
        </SheetContent>
      </Sheet>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-border bg-card flex h-12 shrink-0 items-center justify-between border-b px-3 lg:hidden">
          <Button variant="ghost" size="icon-sm" aria-label="Open menu" onClick={() => setDrawerPath(pathname)}>
            <Menu />
          </Button>
          <Wordmark name={runtimeEnv().productName} className="[&_svg]:size-6" />
          <ThemeMenu />
        </header>
        <main id="main" tabIndex={-1} className="scroll-quiet min-h-0 flex-1 overflow-y-auto outline-none">
          {content}
        </main>
      </div>
    </div>
  );
}
