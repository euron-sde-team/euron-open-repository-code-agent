"use client";

import { Check, Download, FlaskConical, GitBranch, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { RelativeTime } from "@/components/domain/relative-time";
import { PatchStatusBadge } from "@/components/domain/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/input";
import { apiUrl, ws } from "@/lib/api";
import { wsPath } from "@/lib/navigation";
import { useApplyPatch, useDecidePatch, useTestPatch } from "@/lib/queries";
import type { Patch, TaskDetail } from "@/lib/types";
import { useActiveWorkspace, useCan } from "@/lib/workspace-context";

/** The decision: approve or reject with a note, apply an approved patch to a branch, export. */
export function ReviewCard({ patch, task }: { patch: Patch; task: TaskDetail }) {
  const { slug } = useActiveWorkspace();
  const router = useRouter();
  const canApply = useCan("maintainer");
  const canTest = useCan("developer");
  const decide = useDecidePatch(slug, patch.id);
  const apply = useApplyPatch(slug, patch.id);
  const test = useTestPatch(slug, patch.id);
  const [note, setNote] = useState("");
  const [branch, setBranch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const proposed = patch.status === "proposed";
  const isCurrent = task.patches[0]?.id === patch.id;
  const exportUrl = (format: "patch" | "diff") => apiUrl(`${ws(slug)}/patches/${patch.id}/export?format=${format}`);

  async function run(action: () => Promise<unknown>, success: string) {
    setError(null);
    try {
      await action();
      toast.success(success);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That did not work.");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review</CardTitle>
        <PatchStatusBadge status={patch.status} />
      </CardHeader>
      <CardContent className="space-y-4 text-[13px]">
        {proposed && isCurrent ? (
          task.can_approve ? (
            <div className="space-y-3">
              <Textarea
                aria-label="Decision note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Optional note for the record"
                rows={2}
                maxLength={4000}
              />
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  loading={decide.isPending}
                  onClick={() => run(() => decide.mutateAsync({ verb: "approve", note }), "Patch approved")}
                >
                  <Check /> Approve
                </Button>
                <Button
                  className="flex-1"
                  variant="secondary"
                  loading={decide.isPending}
                  onClick={() => run(() => decide.mutateAsync({ verb: "reject", note }), "Patch rejected")}
                >
                  <X /> Reject
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground">
              {canApply
                ? "This workspace requires an independent review: the person who asked for the change cannot decide it."
                : "A maintainer approves or rejects proposed patches."}
            </p>
          )
        ) : null}

        {proposed && !isCurrent ? <p className="text-muted-foreground">A newer revision replaced this one.</p> : null}

        {patch.decided_at ? (
          <div>
            <p>
              {patch.status === "rejected" ? "Rejected" : "Approved"} by{" "}
              <span className="font-medium">{patch.decided_by ?? "a maintainer"}</span>{" "}
              <RelativeTime iso={patch.decided_at} />
            </p>
            {patch.decision_note ? (
              <p className="text-muted-foreground mt-1 italic">&ldquo;{patch.decision_note}&rdquo;</p>
            ) : null}
          </div>
        ) : null}

        {patch.status === "approved" && canApply ? (
          <div className="space-y-2">
            <Input
              aria-label="Branch name"
              value={branch}
              onChange={(event) => setBranch(event.target.value)}
              placeholder={`codeagent/${task.number}-...`}
              className="font-mono text-[12.5px]"
            />
            <Button
              className="w-full"
              loading={apply.isPending}
              onClick={() => run(() => apply.mutateAsync(branch.trim() || undefined), "Applying the patch")}
            >
              <GitBranch /> Apply to a new branch
            </Button>
            <p className="text-muted-foreground text-[12px]">
              Creates a branch from the base commit in CodeAgent&apos;s copy of the repository. Nothing is pushed to
              your git host.
            </p>
          </div>
        ) : null}

        {patch.status === "applying" ? (
          <p className="text-info" role="status">
            Applying to {patch.applied_branch ?? "a branch"}...
          </p>
        ) : null}

        {patch.status === "applied" && patch.applied_branch ? (
          <div className="bg-success-soft rounded-lg px-3 py-2">
            <p className="text-success font-medium">Applied to a branch</p>
            <p className="mt-1 font-mono text-[12.5px] break-all">{patch.applied_branch}</p>
            {patch.applied_commit ? (
              <p className="text-muted-foreground mt-0.5 font-mono text-[12px]">{patch.applied_commit.slice(0, 12)}</p>
            ) : null}
            <p className="text-muted-foreground mt-1.5 text-[12px]">
              Export the patch below and merge it through your usual review.
            </p>
          </div>
        ) : null}

        {patch.apply_error ? <ErrorNotice message={`Applying failed: ${patch.apply_error}`} /> : null}
        {error ? <ErrorNotice message={error} /> : null}

        <div className="border-border flex flex-wrap gap-2 border-t pt-3">
          {canTest && patch.status !== "superseded" ? (
            <Button
              variant="secondary"
              size="sm"
              loading={test.isPending}
              onClick={() =>
                run(async () => {
                  const created = await test.mutateAsync();
                  router.push(wsPath(slug, "runs", String(created.number)));
                }, "Test run queued")
              }
            >
              <FlaskConical /> Run tests
            </Button>
          ) : null}
          <Button asChild variant="secondary" size="sm">
            <a href={exportUrl("patch")} download>
              <Download /> .patch
            </a>
          </Button>
          <Button asChild variant="secondary" size="sm">
            <a href={exportUrl("diff")} download>
              <Download /> .diff
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
