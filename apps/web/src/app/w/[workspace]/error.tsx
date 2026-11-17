"use client";

import { ErrorState } from "@/components/ui/feedback";

export default function WorkspaceError({ error, reset }: { error: Error; reset: () => void }) {
  return <ErrorState className="py-24" message={error.message || "This page failed to render."} onRetry={reset} />;
}
