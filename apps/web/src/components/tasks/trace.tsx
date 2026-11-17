import { AlertCircle, CheckCircle2, Circle, Gavel } from "lucide-react";

import { RelativeTime } from "@/components/domain/relative-time";
import { cn } from "@/lib/cn";
import type { TraceEvent } from "@/lib/types";

const KIND = {
  success: { icon: CheckCircle2, color: "text-success" },
  error: { icon: AlertCircle, color: "text-danger" },
  review: { icon: Gavel, color: "text-primary" },
  info: { icon: Circle, color: "text-subtle" },
} as const;

/** What the agent did, in order, as the worker recorded it. */
export function Trace({ events }: { events: TraceEvent[] }) {
  return (
    <ol className="space-y-0" aria-label="Agent trace">
      {events.map((event, index) => {
        const { icon: Icon, color } = KIND[event.kind as keyof typeof KIND] ?? KIND.info;
        return (
          <li key={`${event.at}-${index}`} className="relative flex gap-3 pb-3 last:pb-0">
            {index < events.length - 1 ? (
              <span className="bg-border absolute top-5 left-[7px] h-[calc(100%-1rem)] w-px" aria-hidden />
            ) : null}
            <Icon className={cn("bg-card relative mt-0.5 size-3.5 shrink-0", color)} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="text-[13px] break-words">{event.message}</p>
              <RelativeTime iso={event.at} className="text-subtle text-[11.5px]" />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
