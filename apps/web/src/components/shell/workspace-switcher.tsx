"use client";

import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/input";
import { wsPath } from "@/lib/navigation";
import { useCreateWorkspace } from "@/lib/queries";
import type { WorkspaceSummary } from "@/lib/types";

export function CreateWorkspaceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const create = useCreateWorkspace({ silent: true });
  const [name, setName] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const created = await create.mutateAsync({ name });
      onOpenChange(false);
      setName("");
      router.push(wsPath(created.slug));
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Create a workspace"
        description="A workspace groups repositories, people and their history."
      >
        <form onSubmit={submit} className="space-y-4">
          <Field label="Name" htmlFor="workspace-name" required>
            <Input
              id="workspace-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Platform engineering"
              maxLength={120}
              required
              autoFocus
            />
          </Field>
          {create.error ? <ErrorNotice message={create.error.message} /> : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
              Create workspace
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function WorkspaceSwitcher({ current, all }: { current: WorkspaceSummary; all: WorkspaceSummary[] }) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`Workspace: ${current.name}. Switch workspace`}
            className="border-border bg-card hover:bg-muted flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left shadow-sm transition-colors"
          >
            <span className="bg-accent text-accent-foreground flex size-7 shrink-0 items-center justify-center rounded-md text-[12px] font-semibold">
              {current.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13.5px] leading-tight font-medium">{current.name}</span>
              <span className="text-muted-foreground block truncate text-[11.5px] capitalize">{current.role}</span>
            </span>
            <ChevronsUpDown className="text-subtle size-4 shrink-0" aria-hidden />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
          {all.map((workspace) => (
            <DropdownMenuItem key={workspace.id} onSelect={() => router.push(wsPath(workspace.slug))}>
              <span className="min-w-0 flex-1 truncate">{workspace.name}</span>
              {workspace.slug === current.slug ? <Check className="text-primary" /> : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCreating(true)}>
            <Plus /> New workspace
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <CreateWorkspaceDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}
