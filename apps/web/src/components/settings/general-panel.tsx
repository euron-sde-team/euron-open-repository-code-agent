"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldHint, Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useUpdateWorkspace } from "@/lib/queries";
import type { WorkspaceSettings } from "@/lib/types";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";

export function GeneralPanel() {
  const { slug, workspace } = useActiveWorkspace();
  const canEdit = useCan("owner");
  const update = useUpdateWorkspace(slug);
  const [name, setName] = useState(workspace.name);
  const [description, setDescription] = useState(workspace.description);
  const [settings, setSettings] = useState<WorkspaceSettings>(workspace.settings);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await update.mutateAsync({ name: name.trim(), description: description.trim(), settings });
    toast.success("Workspace saved");
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Workspace</CardTitle>
            <CardDescription>Repositories, people and their history live in one workspace.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Name" htmlFor="ws-name">
            <Input
              id="ws-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              disabled={!canEdit}
              required
            />
          </Field>
          <Field label="Description" htmlFor="ws-description">
            <Textarea
              id="ws-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              maxLength={1000}
              disabled={!canEdit}
            />
          </Field>
          <p className="text-muted-foreground text-[12.5px]">
            Address: <code className="bg-muted rounded px-1 font-mono text-[12px]">{slug}</code>
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Agent and review</CardTitle>
            <CardDescription>How tasks are planned and who may approve what they propose.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex items-start justify-between gap-6">
            <div>
              <label htmlFor="independent" className="text-[13.5px] font-medium">
                Require an independent review
              </label>
              <FieldHint>The person who asked for a change cannot approve or reject its patch.</FieldHint>
            </div>
            <Switch
              id="independent"
              checked={settings.require_independent_review}
              onCheckedChange={(checked) => setSettings({ ...settings, require_independent_review: checked })}
              disabled={!canEdit}
            />
          </div>
          <div className="flex items-start justify-between gap-6">
            <div>
              <label htmlFor="baseline" className="text-[13.5px] font-medium">
                Run the tests before the agent changes anything
              </label>
              <FieldHint>
                The baseline shows which failures were already there, so a reviewer sees what the change fixed or broke.
              </FieldHint>
            </div>
            <Switch
              id="baseline"
              checked={settings.run_baseline_tests}
              onCheckedChange={(checked) => setSettings({ ...settings, run_baseline_tests: checked })}
              disabled={!canEdit}
            />
          </div>
          <Field
            label="Planner and answerer"
            htmlFor="agent-mode"
            hint="Automatic uses the model the deployment is configured with, if any. Local never calls a model: the same inputs always give the same output."
          >
            <NativeSelect
              id="agent-mode"
              value={settings.agent_mode}
              onChange={(e) =>
                setSettings({ ...settings, agent_mode: e.target.value as WorkspaceSettings["agent_mode"] })
              }
              disabled={!canEdit}
              className="max-w-xs"
            >
              <option value="auto">Automatic</option>
              <option value="local">Always local and offline</option>
            </NativeSelect>
          </Field>
        </CardContent>
      </Card>
      {canEdit ? (
        <div className="flex justify-end">
          <Button type="submit" loading={update.isPending} disabled={!name.trim()}>
            Save changes
          </Button>
        </div>
      ) : (
        <p className="text-muted-foreground text-[13px]">Only an owner can change these settings.</p>
      )}
    </form>
  );
}
