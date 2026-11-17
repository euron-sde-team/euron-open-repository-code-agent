"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { PasswordForm } from "@/components/shell/password-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { useUpdateProfile } from "@/lib/queries";
import { useActiveWorkspace } from "@/lib/workspace-context";

export function AccountPanel() {
  const { me, role } = useActiveWorkspace();
  const update = useUpdateProfile();
  const [name, setName] = useState(me.user.name);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await update.mutateAsync({ name: name.trim() });
    toast.success("Profile saved");
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Profile</CardTitle>
            <CardDescription>
              Signed in as {me.user.email}, {role} in this workspace.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <Field label="Name" htmlFor="profile-name" className="min-w-56 flex-1 sm:max-w-sm">
              <Input
                id="profile-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={120}
                required
              />
            </Field>
            <Button type="submit" loading={update.isPending} disabled={!name.trim() || name.trim() === me.user.name}>
              Save
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Password</CardTitle>
            <CardDescription>Changing it signs out every other browser and device.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <div className="max-w-sm">
            <PasswordForm idPrefix="account-password" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
