"use client";

import { Fragment, useState } from "react";

import { RelativeTime } from "@/components/domain/relative-time";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { humanize } from "@/lib/format";
import { useAudit } from "@/lib/queries";
import { useActiveWorkspace } from "@/lib/workspace-context";

const PAGE = 25;

function summarize(details: Record<string, unknown>): string {
  return Object.entries(details)
    .filter(([, value]) => typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    .slice(0, 3)
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${String(value)}`)
    .join(", ");
}

export function ActivityPanel() {
  const { slug } = useActiveWorkspace();
  const [offset, setOffset] = useState(0);
  const audit = useAudit(slug, { limit: PAGE, offset });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {audit.error ? (
          <ErrorState message={audit.error.message} onRetry={() => audit.refetch()} />
        ) : !audit.data ? (
          <div className="px-5 pb-5">
            <Skeleton className="h-40" />
          </div>
        ) : audit.data.length === 0 ? (
          <EmptyState title="Nothing recorded yet" className="py-8" />
        ) : (
          <>
            <TableContainer label="Audit trail">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Who</TableHead>
                    <TableHead>What</TableHead>
                    <TableHead>Details</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {audit.data.map((event) => (
                    <Fragment key={event.id}>
                      <TableRow>
                        <TableCell className="text-muted-foreground whitespace-nowrap">
                          <RelativeTime iso={event.created_at} />
                        </TableCell>
                        <TableCell>{event.actor_name ?? "System"}</TableCell>
                        <TableCell className="font-medium">{humanize(event.action)}</TableCell>
                        <TableCell className="text-muted-foreground max-w-xs truncate">
                          {summarize(event.details)}
                        </TableCell>
                      </TableRow>
                    </Fragment>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <div className="border-border flex items-center justify-between border-t px-5 py-3">
              <Button
                variant="secondary"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                Newer
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={audit.data.length < PAGE}
                onClick={() => setOffset(offset + PAGE)}
              >
                Older
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
