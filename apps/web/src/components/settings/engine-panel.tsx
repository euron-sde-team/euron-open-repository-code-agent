"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { SKILL_LABEL } from "@/lib/labels";
import { useSystemInfo } from "@/lib/queries";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-1 py-2.5 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4">
      <dt className="text-muted-foreground text-[13px]">{label}</dt>
      <dd className="text-[13.5px]">{children}</dd>
    </div>
  );
}

/** What this deployment runs on: the answerer, the planner, the embedder and the sandbox. */
export function EnginePanel() {
  const system = useSystemInfo();
  if (system.error) return <ErrorState message={system.error.message} onRetry={() => system.refetch()} />;
  const info = system.data;
  if (!info) return <Skeleton className="h-72" />;
  const offline = !info.answerer.uses_model;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Models</CardTitle>
            <CardDescription>Configured by the deployment, not by the workspace.</CardDescription>
          </div>
          <Badge tone={offline ? "success" : "info"}>
            {offline ? "Offline, no model calls" : `Model: ${info.answerer.label}`}
          </Badge>
        </CardHeader>
        <CardContent>
          <dl className="divide-border divide-y">
            <Row label="Answers">
              {offline
                ? "The local answerer reads the index and composes a cited answer. Deterministic, no network."
                : `${info.answerer.provider}, model ${info.answerer.model}`}
            </Row>
            <Row label="Agent planner">
              {offline ? (
                <span>
                  The local planner has {info.skills.length} skills:{" "}
                  {info.skills
                    .map((s) => SKILL_LABEL[s] ?? s)
                    .join(", ")
                    .toLowerCase()}
                  .
                </span>
              ) : (
                `${info.planner.provider}, model ${info.planner.model}, with search-and-replace edits and a test feedback loop`
              )}
            </Row>
            <Row label="Embeddings">
              {info.embeddings}, {info.embedding_dim} dimensions
            </Row>
            <Row label="Catalogued helpers">
              <span className="font-mono text-[12.5px]">{info.helpers.join(", ")}</span>
            </Row>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Sandbox</CardTitle>
            <CardDescription>Repository code only ever runs here.</CardDescription>
          </div>
          <Badge tone="primary">{info.sandbox.backend}</Badge>
        </CardHeader>
        <CardContent>
          <dl className="divide-border divide-y">
            <Row label="Network">
              None: {info.sandbox.network === "none" ? "the run has no route out" : info.sandbox.network}
            </Row>
            <Row label="Time limit">{info.sandbox.timeout_s} seconds</Row>
            <Row label="Memory">{info.sandbox.memory_mb} MB</Row>
            <Row label="CPU">
              {info.sandbox.cpus} core{info.sandbox.cpus === 1 ? "" : "s"}
            </Row>
            {info.sandbox.image ? (
              <Row label="Image">
                <code className="font-mono text-[12.5px]">{info.sandbox.image}</code>
              </Row>
            ) : null}
            <Row label="Archives up to">{info.max_archive_mb} MB</Row>
          </dl>
        </CardContent>
      </Card>
      <p className="text-subtle text-[12px]">CodeAgent {info.version}</p>
    </div>
  );
}
