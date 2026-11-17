"use client";

import { KeyRound, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CodeBlock, CopyField } from "@/components/copy-field";
import { RelativeTime } from "@/components/domain/relative-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { EmptyState, ErrorNotice, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from "@/lib/queries";
import { runtimeEnv } from "@/lib/runtime-env";
import { askExample, curlExample } from "@/lib/snippets";
import type { ApiKey, ApiKeyCreated } from "@/lib/types";
import { useActiveWorkspace } from "@/lib/workspace-context";

function CreateKeyDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { slug } = useActiveWorkspace();
  const create = useCreateApiKey(slug, { silent: true });
  const [name, setName] = useState("");
  const [role, setRole] = useState<"viewer" | "developer">("viewer");
  const [days, setDays] = useState("");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setCreated(
        await create.mutateAsync({
          name: name.trim(),
          role,
          expires_in_days: days ? Number(days) : undefined,
        }),
      );
    } catch {
      // Rendered from the mutation state.
    }
  }

  function close() {
    onOpenChange(false);
    setCreated(null);
    setName("");
    setDays("");
    create.reset();
  }

  const apiUrl = runtimeEnv().apiUrl;
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent
        title={created ? "Your new API key" : "Create an API key"}
        description={
          created
            ? "Copy it now. Only a keyed hash is stored, so it cannot be shown again."
            : "Keys belong to the workspace, not to a person, so CI can search and ask without a sign-in."
        }
        className="w-[min(94vw,38rem)]"
      >
        {created ? (
          <div className="space-y-4">
            <CopyField label="API key" value={created.key} />
            <div>
              <p className="mb-1.5 text-[13px] font-medium">Search symbols</p>
              <CodeBlock label="Search example" code={curlExample(apiUrl, slug, created.key)} />
            </div>
            <div>
              <p className="mb-1.5 text-[13px] font-medium">Ask a question</p>
              <CodeBlock label="Ask example" code={askExample(apiUrl, slug, created.key)} />
            </div>
            <DialogFooter>
              <Button onClick={close}>I have copied it</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field label="Name" htmlFor="key-name" hint="Where it will be used, for example CI search." required>
              <Input
                id="key-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={80}
                required
                autoFocus
              />
            </Field>
            <Field
              label="Access"
              htmlFor="key-role"
              hint={
                role === "viewer"
                  ? "Search, ask and read tasks, patches and runs."
                  : "Also create tasks and start test runs. It can never approve a patch."
              }
            >
              <NativeSelect
                id="key-role"
                value={role}
                onChange={(e) => setRole(e.target.value as "viewer" | "developer")}
              >
                <option value="viewer">Viewer</option>
                <option value="developer">Developer</option>
              </NativeSelect>
            </Field>
            <Field
              label="Expires after (days)"
              htmlFor="key-days"
              hint="Optional. Leave empty for a key that does not expire."
            >
              <Input
                id="key-days"
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={(e) => setDays(e.target.value)}
              />
            </Field>
            {create.error ? <ErrorNotice message={create.error.message} /> : null}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
                Create key
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function keyState(key: ApiKey): { label: string; tone: "success" | "danger" | "warning" } {
  if (key.revoked_at) return { label: "Revoked", tone: "danger" };
  if (key.expires_at && new Date(key.expires_at).getTime() <= Date.now()) return { label: "Expired", tone: "warning" };
  return { label: "Active", tone: "success" };
}

export function ApiKeysPanel() {
  const { slug } = useActiveWorkspace();
  const keys = useApiKeys(slug);
  const revoke = useRevokeApiKey(slug);
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>API keys</CardTitle>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus /> Create key
        </Button>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {keys.error ? (
          <ErrorState message={keys.error.message} onRetry={() => keys.refetch()} />
        ) : !keys.data ? (
          <div className="px-5 pb-5">
            <Skeleton className="h-16" />
          </div>
        ) : keys.data.length === 0 ? (
          <EmptyState
            icon={<KeyRound />}
            title="No API keys"
            description="Create one to call CodeAgent from CI or a script."
            className="py-8"
          />
        ) : (
          <TableContainer label="API keys">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Access</TableHead>
                  <TableHead>Last used</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.data.map((key) => {
                  const state = keyState(key);
                  return (
                    <TableRow key={key.id}>
                      <TableCell className="font-medium">{key.name}</TableCell>
                      <TableCell className="text-muted-foreground font-mono text-[12px]">
                        cak_{key.prefix}_...
                      </TableCell>
                      <TableCell className="capitalize">{key.role}</TableCell>
                      <TableCell className="text-muted-foreground">
                        <RelativeTime iso={key.last_used_at} />
                      </TableCell>
                      <TableCell>
                        <Badge tone={state.tone}>{state.label}</Badge>
                      </TableCell>
                      <TableCell>
                        {state.label === "Active" ? (
                          <Button variant="danger-ghost" size="sm" onClick={() => setRevoking(key)}>
                            Revoke
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
      <CreateKeyDialog open={creating} onOpenChange={setCreating} />
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke ${revoking?.name ?? "this key"}?`}
        description="Anything using it stops working immediately. This cannot be undone."
        confirmLabel="Revoke key"
        destructive
        onConfirm={async () => {
          if (!revoking) return;
          await revoke.mutateAsync(revoking.id);
          toast.success("Key revoked");
        }}
      />
    </Card>
  );
}
