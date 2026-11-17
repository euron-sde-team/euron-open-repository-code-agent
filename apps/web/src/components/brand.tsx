import { cn } from "@/lib/cn";

/** Code brackets around a cursor: a codebase that answers. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn("size-7", className)}>
      <rect width="64" height="64" rx="16" fill="var(--primary)" />
      <path
        d="M24 21 13 32l11 11M40 21l11 11-11 11"
        fill="none"
        stroke="var(--primary-foreground)"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x="29.5" y="19" width="5" height="26" rx="2.5" fill="var(--primary-foreground)" opacity="0.85" />
    </svg>
  );
}

export function Wordmark({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <BrandMark />
      <span className="text-[15px] font-semibold tracking-tight">{name}</span>
    </span>
  );
}
