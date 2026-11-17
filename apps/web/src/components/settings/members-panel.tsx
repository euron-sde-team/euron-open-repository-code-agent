"use client";

import { Plus, UserMinus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { CopyField } from "@/components/copy-field";
import { RelativeTime } from "@/components/domain/relative-time";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Input, NativeSelect } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ROLES, ROLE_SUMMARY } from "@/lib/capabilities";
import { useAddMember, useChangeMemberRole, useMembers, useRemoveMember } from "@/lib/queries";
import type { Member, Role } from "@/lib/types";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";

function AddMemberDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { slug } = useActiveWorkspace();
  const add = useAddMember(slug, { silent: true });
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("developer");
  const [password, setPassword] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const added = await add.mutateAsync({ email: email.trim(), name: name.trim() || undefined, role });
      toast.success(`${added.member.name} added as ${added.member.role}`);
      if (added.temporary_password) setPassword(added.temporary_password);
      else close();
    } catch {
      // Rendered from the mutation state.
    }
  }

  function close() {
    onOpenChange(false);
    setEmail("");
    setName("");
    setPassword(null);
    add.reset();
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent
        title={password ? "Share the temporary password" : "Add a person"}
        description={
          password
            ? "An account was created. This password is shown once; they should change it after signing in."
            : "They get an account if they do not have one, and the role you choose."
        }
      >
        {password ? (
          <div className="space-y-4">
            <CopyField label="Temporary password" value={password} />
            <DialogFooter>
              <Button onClick={close}>Done</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <Field label="Email" htmlFor="member-email" required>
              <Input
                id="member-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </Field>
            <Field label="Name" htmlFor="member-name" hint="Used only when a new account is created.">
              <Input id="member-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
            </Field>
            <Field label="Role" htmlFor="member-role" hint={ROLE_SUMMARY[role]}>
              <NativeSelect id="member-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            {add.error ? <ErrorNotice message={add.error.message} /> : null}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" loading={add.isPending} disabled={!email.trim()}>
                Add person
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function MembersPanel() {
  const { slug, me } = useActiveWorkspace();
  const isOwner = useCan("owner");
  const members = useMembers(slug);
  const change = useChangeMemberRole(slug);
  const remove = useRemoveMember(slug);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Member | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>People</CardTitle>
        {isOwner ? (
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus /> Add person
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {members.error ? (
          <ErrorState message={members.error.message} onRetry={() => members.refetch()} />
        ) : !members.data ? (
          <div className="space-y-2 px-5 pb-5">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : (
          <TableContainer label="Members">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Person</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Joined</TableHead>
                  <TableHead className="w-12">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.data.map((member) => (
                  <TableRow key={member.user_id}>
                    <TableCell>
                      <span className="block font-medium">{member.name}</span>
                      <span className="text-muted-foreground block text-[12.5px]">{member.email}</span>
                    </TableCell>
                    <TableCell>
                      {isOwner ? (
                        <NativeSelect
                          aria-label={`Role of ${member.name}`}
                          value={member.role}
                          onChange={(event) =>
                            change.mutate({ userId: member.user_id, role: event.target.value as Role })
                          }
                          className="h-8 w-auto text-[13px]"
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </NativeSelect>
                      ) : (
                        <span className="capitalize">{member.role}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <RelativeTime iso={member.joined_at} />
                    </TableCell>
                    <TableCell>
                      {isOwner && member.user_id !== me.user.id ? (
                        <Button
                          variant="danger-ghost"
                          size="icon-sm"
                          aria-label={`Remove ${member.name}`}
                          onClick={() => setRemoving(member)}
                        >
                          <UserMinus />
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
        <dl className="border-border text-muted-foreground grid gap-x-6 gap-y-1.5 border-t px-5 py-4 text-[12.5px] sm:grid-cols-2">
          {ROLES.map((role) => (
            <div key={role}>
              <dt className="text-foreground inline font-medium capitalize">{role}: </dt>
              <dd className="inline">{ROLE_SUMMARY[role]}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
      <AddMemberDialog open={adding} onOpenChange={setAdding} />
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Remove ${removing?.name ?? "this person"}?`}
        description="They lose access to this workspace immediately. Their past comments and decisions stay."
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          if (!removing) return;
          await remove.mutateAsync(removing.user_id);
          toast.success(`${removing.name} removed`);
        }}
      />
    </Card>
  );
}
