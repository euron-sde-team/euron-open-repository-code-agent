"use client";

import { FolderPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CreateWorkspaceDialog } from "@/components/shell/workspace-switcher";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/feedback";
import { ApiError } from "@/lib/api";
import { wsPath } from "@/lib/navigation";
import { pickWorkspace } from "@/lib/workspace-choice";
import { useMe, useSystemInfo } from "@/lib/queries";
import { LAST_WORKSPACE_KEY, readLocal } from "@/lib/storage";

/** Sends people where they belong: first-run setup, sign-in, or their last workspace. */
export default function Home() {
  const router = useRouter();
  const system = useSystemInfo();
  // A fresh deployment has nobody to sign in: do not ask who is signed in until it is set up.
  const me = useMe(system.data?.needs_setup === false);
  const [creating, setCreating] = useState(false);
  const settled = !system.isFetching && !me.isFetching;
  const unauthorized = me.error instanceof ApiError && me.error.status === 401;

  useEffect(() => {
    // Decide only on fresh answers: a refetch after signing in still holds the old 401.
    if (!settled) return;
    if (system.data?.needs_setup) {
      router.replace("/welcome");
    } else if (system.data && unauthorized) {
      router.replace("/login");
    } else if (me.data) {
      const target = pickWorkspace(me.data.workspaces, readLocal(LAST_WORKSPACE_KEY));
      if (target) router.replace(wsPath(target.slug));
    }
  }, [settled, system.data, unauthorized, me.data, router]);

  const failure = system.error ?? (unauthorized ? null : me.error);
  if (failure) {
    return (
      <ErrorState
        className="min-h-dvh"
        title="CodeAgent is unreachable"
        message={failure.message}
        onRetry={() => {
          void system.refetch();
          void me.refetch();
        }}
      />
    );
  }
  if (me.data && me.data.workspaces.length === 0) {
    return (
      <main>
        <EmptyState
          className="min-h-dvh"
          icon={<FolderPlus />}
          title="No workspaces yet"
          description="A workspace groups repositories, people and their history. Create one, or ask an owner to add you to theirs."
          action={<Button onClick={() => setCreating(true)}>Create a workspace</Button>}
        />
        <CreateWorkspaceDialog open={creating} onOpenChange={setCreating} />
      </main>
    );
  }
  return (
    <main className="flex min-h-dvh items-center justify-center" role="status" aria-label="Loading">
      <Spinner className="size-5" />
    </main>
  );
}
