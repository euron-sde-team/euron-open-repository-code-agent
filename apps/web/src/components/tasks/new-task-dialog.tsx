"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, NativeSelect, Input, Textarea } from "@/components/ui/input";
import { wsPath } from "@/lib/navigation";
import { useCreateTask, useRepositories, useSystemInfo } from "@/lib/queries";
import { useActiveWorkspace } from "@/lib/workspace-context";

const TEMPLATES = [
  { label: "Rename a symbol", title: "Rename ", description: "rename `old_name` to `new_name`" },
  {
    label: "Fix a failing test",
    title: "Fix the failing test",
    description: "Fix the failing test: make the tests pass.",
  },
  { label: "Add a helper", title: "Add a helper function", description: "add `clamp` to the package's utils module" },
];

/** Describe a change: the agent plans it, edits, runs the tests and proposes a patch. */
export function NewTaskDialog({
  open,
  onOpenChange,
  repository,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  repository?: string;
}) {
  const { slug } = useActiveWorkspace();
  const router = useRouter();
  const repositories = useRepositories(slug, { status: "ready", limit: 100 });
  const system = useSystemInfo();
  const create = useCreateTask(slug, { silent: true });
  const [repo, setRepo] = useState(repository ?? "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const items = repositories.data?.items ?? [];
  const chosen = repo || items[0]?.slug || "";
  const offline = system.data ? !system.data.planner.uses_model : true;

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const task = await create.mutateAsync({
        repository: chosen,
        title: title.trim(),
        description: description.trim(),
      });
      toast.success(`Task #${task.number} queued`);
      onOpenChange(false);
      setTitle("");
      setDescription("");
      router.push(wsPath(slug, "tasks", String(task.number)));
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="New task"
        description="The agent proposes a patch with its reasoning and test results. Nothing is applied until a maintainer approves it."
        className="w-[min(94vw,36rem)]"
      >
        <form onSubmit={submit} className="space-y-4">
          <Field label="Repository" htmlFor="task-repo" required>
            <NativeSelect id="task-repo" value={chosen} onChange={(event) => setRepo(event.target.value)} required>
              {items.length === 0 ? <option value="">No indexed repository</option> : null}
              {items.map((r) => (
                <option key={r.id} value={r.slug}>
                  {r.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <div>
            <p className="text-muted-foreground mb-1.5 text-[12.5px]">
              {offline
                ? "Offline planner. It understands these requests:"
                : "Start from a template, or describe anything:"}
            </p>
            <ul className="flex flex-wrap gap-1.5">
              {TEMPLATES.map((template) => (
                <li key={template.label}>
                  <button
                    type="button"
                    onClick={() => {
                      setTitle(template.title);
                      setDescription(template.description);
                    }}
                    className="border-border bg-card hover:bg-muted rounded-full border px-2.5 py-1 text-[12px] transition-colors"
                  >
                    {template.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <Field label="Title" htmlFor="task-title" required>
            <Input
              id="task-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              minLength={3}
              maxLength={200}
              required
            />
          </Field>
          <Field
            label="Description"
            htmlFor="task-description"
            hint={
              offline
                ? "Use backticks around names: rename `apply_discount` to `apply_threshold_discount`."
                : "What should change, and why."
            }
          >
            <Textarea
              id="task-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={4}
              maxLength={8000}
            />
          </Field>
          {create.error ? <ErrorNotice message={create.error.message} /> : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!chosen || title.trim().length < 3}>
              Create task
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
