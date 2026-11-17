import { Skeleton } from "@/components/ui/feedback";

export default function Loading() {
  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 px-4 py-8 sm:px-6 lg:px-10" aria-busy>
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-72" />
    </div>
  );
}
