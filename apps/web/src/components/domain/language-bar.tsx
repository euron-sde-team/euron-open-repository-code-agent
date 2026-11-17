import { SERIES } from "@/components/charts";
import { formatPercent } from "@/lib/format";
import type { LanguageStat } from "@/lib/types";

/** How a repository divides by language: one proportional bar and a legend. */
export function LanguageBar({ languages, max = 5 }: { languages: Record<string, LanguageStat>; max?: number }) {
  const entries = Object.entries(languages)
    .map(([name, stat]) => ({ name, bytes: stat.bytes }))
    .sort((a, b) => b.bytes - a.bytes);
  const total = entries.reduce((sum, e) => sum + e.bytes, 0);
  if (total === 0) return null;
  const shown = entries.slice(0, max);
  const rest = entries.slice(max).reduce((sum, e) => sum + e.bytes, 0);
  const parts = rest > 0 ? [...shown, { name: "Other", bytes: rest }] : shown;
  return (
    <div>
      <div
        className="bg-muted flex h-1.5 overflow-hidden rounded-full"
        role="img"
        aria-label={`Languages: ${parts.map((p) => `${p.name} ${formatPercent(p.bytes / total)}`).join(", ")}`}
      >
        {parts.map((part, index) => (
          <span
            key={part.name}
            style={{ width: `${(part.bytes / total) * 100}%`, background: SERIES[index % SERIES.length] }}
          />
        ))}
      </div>
      <ul className="text-muted-foreground mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
        {parts.map((part, index) => (
          <li key={part.name} className="flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ background: SERIES[index % SERIES.length] }} aria-hidden />
            {part.name} <span className="tabular">{formatPercent(part.bytes / total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
