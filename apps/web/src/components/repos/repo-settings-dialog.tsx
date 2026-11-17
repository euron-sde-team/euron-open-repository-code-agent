"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/input";
import { useUpdateRepository } from "@/lib/queries";
import type { RepositoryDetail } from "@/lib/types";

function intOrNull(value: string): number | null {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

export function RepoSettingsDialog({
  workspace,
  repository,
  open,
  onOpenChange,
}: {
  workspace: string;
  repository: RepositoryDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const update = useUpdateRepository(workspace, repository.slug);
  const [name, setName] = useState(repository.name);
  const [description, setDescription] = useState(repository.description);
  const [command, setCommand] = useState(repository.settings.test_command ?? "");
  const [timeout, setTimeoutValue] = useState(repository.settings.test_timeout_s?.toString() ?? "");
  const [memory, setMemory] = useState(repository.settings.memory_mb?.toString() ?? "");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({
        name: name.trim(),
        description: description.trim(),
        settings: {
          test_command: command.trim() || null,
          test_timeout_s: intOrNull(timeout),
          memory_mb: intOrNull(memory),
        },
      });
      toast.success("Repository settings saved");
      onOpenChange(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the settings.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Repository settings"
        description="How this repository is described and how its tests run in the sandbox."
        className="w-[min(94vw,36rem)]"
      >
        <form onSubmit={submit} className="space-y-4">
          <Field label="Name" htmlFor="settings-name" required>
            <Input id="settings-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
          </Field>
          <Field label="Description" htmlFor="settings-description">
            <Textarea
              id="settings-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={1000}
              rows={2}
            />
          </Field>
          <Field
            label="Test command"
            htmlFor="settings-command"
            hint="Run from the repository root inside the sandbox. Leave empty to disable test runs."
          >
            <Input
              id="settings-command"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              className="font-mono text-[13px]"
              placeholder="python -m pytest -q"
            />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Time limit (seconds)" htmlFor="settings-timeout" hint="Capped by the deployment.">
              <Input
                id="settings-timeout"
                type="number"
                min={5}
                max={3600}
                value={timeout}
                onChange={(e) => setTimeoutValue(e.target.value)}
                placeholder="Deployment default"
              />
            </Field>
            <Field label="Memory limit (MB)" htmlFor="settings-memory" hint="Capped by the deployment.">
              <Input
                id="settings-memory"
                type="number"
                min={64}
                max={16384}
                value={memory}
                onChange={(e) => setMemory(e.target.value)}
                placeholder="Deployment default"
              />
            </Field>
          </div>
          {error ? <ErrorNotice message={error} /> : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={update.isPending} disabled={!name.trim()}>
              Save settings
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
