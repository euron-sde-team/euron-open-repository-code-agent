const numberFormat = new Intl.NumberFormat("en-US");
const compactFormat = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export const formatNumber = (value: number): string => numberFormat.format(value);

export const formatCompact = (value: number): string =>
  value < 10_000 ? numberFormat.format(value) : compactFormat.format(value);

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export const formatPercent = (ratio: number, digits = 0): string => `${(ratio * 100).toFixed(digits)}%`;

/** Milliseconds as "420 ms", "1.4 s" or "12 s". */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
}

export const pluralize = (count: number, singular: string, plural = `${singular}s`): string =>
  `${formatNumber(count)} ${count === 1 ? singular : plural}`;

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31_536_000],
  ["month", 2_592_000],
  ["week", 604_800],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "3 days ago", "in 2 hours", "just now". */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

/**
 * A compact age for dense tables: "5m", "3h", "9d", "6w", "4mo", "2y". Future times
 * (an event that has not happened yet) read as "in 3d".
 */
export function formatAge(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  const absolute = Math.abs(seconds);
  const prefix = seconds < 0 ? "in " : "";
  if (absolute < 60) return seconds < 0 ? "in <1m" : "now";
  const minutes = Math.floor(absolute / 60);
  if (minutes < 60) return `${prefix}${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${prefix}${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 14) return `${prefix}${days}d`;
  if (days < 56) return `${prefix}${Math.floor(days / 7)}w`;
  if (days < 365) return `${prefix}${Math.floor(days / 30)}mo`;
  return `${prefix}${Math.floor(days / 365)}y`;
}

type DateOptions = { timeZone?: string };

/** "Oct 23, 2026". */
export function formatDate(iso: string, { timeZone }: DateOptions = {}): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone,
  });
}

/** "Oct 23, 2026, 3:04 PM". */
export function formatDateTime(iso: string, { timeZone }: DateOptions = {}): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });
}

/** A calendar day as the API sends it ("2026-10-23") to "Oct 23". */
export function formatDay(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase() || "?";
}

/** Shorten long text for a table cell; the full text belongs in a title or tooltip. */
export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 3)).trimEnd()}...`;
}

/** "user_request" to "User request". */
export function humanize(value: string): string {
  const spaced = value.replace(/[_.:-]+/g, " ").trim();
  return spaced ? spaced[0]!.toUpperCase() + spaced.slice(1) : spaced;
}
