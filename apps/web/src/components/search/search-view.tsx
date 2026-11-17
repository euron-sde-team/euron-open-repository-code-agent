"use client";

import { Braces, Regex, Sparkles, TextSearch as TextIcon } from "lucide-react";
import { Suspense, useState } from "react";

import { SemanticResults, SymbolResults, TextResults } from "@/components/search/search-results";
import { Checkbox } from "@/components/ui/checkbox";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { Input, NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { SearchField } from "@/components/ui/filter-bar";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { SYMBOL_KIND_LABEL } from "@/lib/labels";
import { useRepositories, useSemanticSearch, useSymbolSearch, useTextSearch } from "@/lib/queries";
import { SEARCH_MODE_KEY, readLocal, writeLocal } from "@/lib/storage";
import type { SearchMode } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced";
import { useUrlParams } from "@/lib/use-url-params";
import { useActiveWorkspace } from "@/lib/workspace-context";
import { formatNumber } from "@/lib/format";

const MODES: { value: SearchMode; label: string; icon: typeof Braces; hint: string }[] = [
  { value: "symbols", label: "Symbols", icon: Braces, hint: "Find a class, function or constant by name." },
  { value: "text", label: "Text", icon: TextIcon, hint: "Find lines of code, literally or by regular expression." },
  { value: "semantic", label: "By meaning", icon: Sparkles, hint: "Describe what the code does, in your own words." },
];

function isMode(value: string | null): value is SearchMode {
  return value === "symbols" || value === "text" || value === "semantic";
}

function SearchBody() {
  const { slug } = useActiveWorkspace();
  const { get, update } = useUrlParams();
  const stored = readLocal(SEARCH_MODE_KEY);
  const rawMode = get("mode") ?? stored;
  const mode: SearchMode = isMode(rawMode) ? rawMode : "symbols";
  const [text, setText] = useState(get("q") ?? "");
  const q = useDebouncedValue(text, 250);
  const repository = get("repo") ?? "";
  const kind = get("kind") ?? "";
  const regex = get("regex") === "1";
  const caseSensitive = get("case") === "1";
  const path = get("path") ?? "";
  const debouncedPath = useDebouncedValue(path, 300);
  const repositories = useRepositories(slug, { status: "ready", limit: 100 });

  const symbols = useSymbolSearch(
    slug,
    mode === "symbols" ? { q, repository: repository || undefined, kind: kind || undefined } : { q: "" },
  );
  const textual = useTextSearch(
    slug,
    mode === "text"
      ? {
          q,
          regex,
          case_sensitive: caseSensitive,
          repository: repository || undefined,
          path: debouncedPath || undefined,
        }
      : { q: "" },
  );
  const semantic = useSemanticSearch(
    slug,
    mode === "semantic" ? { q, repository: repository || undefined } : { q: "" },
  );
  const active = mode === "symbols" ? symbols : mode === "text" ? textual : semantic;
  const info = MODES.find((m) => m.value === mode);
  const took = active.data?.took_ms;

  return (
    <PageBody>
      <PageHeader title="Search" description="Find definitions, lines and ideas across every ready repository." />
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl<SearchMode>
            label="Search mode"
            value={mode}
            onValueChange={(next) => {
              writeLocal(SEARCH_MODE_KEY, next);
              update({ mode: next });
            }}
            options={MODES.map((m) => ({
              value: m.value,
              label: (
                <>
                  <m.icon /> {m.label}
                </>
              ),
            }))}
          />
          <p className="text-muted-foreground text-[13px]">{info?.hint}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SearchField
            value={text}
            onChange={(value) => {
              setText(value);
              update({ q: value });
            }}
            label={mode === "semantic" ? "Describe the code" : mode === "text" ? "Search the code" : "Search symbols"}
            placeholder={
              mode === "semantic" ? "how is sales tax worked out" : mode === "text" ? "def calc_" : "apply_discount"
            }
            className="sm:max-w-md"
          />
          <NativeSelect
            aria-label="Repository"
            value={repository}
            onChange={(event) => update({ repo: event.target.value })}
            className="w-auto min-w-40"
          >
            <option value="">All repositories</option>
            {repositories.data?.items.map((r) => (
              <option key={r.id} value={r.slug}>
                {r.name}
              </option>
            ))}
          </NativeSelect>
          {mode === "symbols" ? (
            <NativeSelect
              aria-label="Kind"
              value={kind}
              onChange={(event) => update({ kind: event.target.value })}
              className="w-auto min-w-32"
            >
              <option value="">Any kind</option>
              {Object.keys(SYMBOL_KIND_LABEL)
                .filter((k) => k !== "module")
                .map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
            </NativeSelect>
          ) : null}
          {mode === "text" ? (
            <>
              <label className="text-muted-foreground flex items-center gap-2 text-[13px]">
                <Checkbox
                  checked={regex}
                  onCheckedChange={(v) => update({ regex: v === true ? "1" : null })}
                  aria-label="Regular expression"
                />
                <Regex className="size-3.5" aria-hidden /> Regex
              </label>
              <label className="text-muted-foreground flex items-center gap-2 text-[13px]">
                <Checkbox
                  checked={caseSensitive}
                  onCheckedChange={(v) => update({ case: v === true ? "1" : null })}
                  aria-label="Match case"
                />
                Match case
              </label>
              <Input
                aria-label="Path glob"
                value={path}
                onChange={(event) => update({ path: event.target.value })}
                placeholder="Path, e.g. src/**/*.py"
                className="w-auto min-w-44 sm:w-56"
              />
            </>
          ) : null}
        </div>
      </div>

      <div className="mt-6" aria-live="polite">
        {!q.trim() ? (
          <p className="text-muted-foreground text-[13.5px]">Type to search. Results link to the exact lines.</p>
        ) : active.error ? (
          <ErrorState title="That search did not run" message={active.error.message} onRetry={() => active.refetch()} />
        ) : !active.data ? (
          <div className="space-y-2" aria-busy>
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : (
          <>
            <p className="text-subtle mb-3 text-[12.5px]">
              {mode === "symbols"
                ? `${formatNumber(symbols.data?.hits.length ?? 0)} symbols`
                : mode === "text"
                  ? `${formatNumber(textual.data?.match_count ?? 0)} matching lines`
                  : `${formatNumber(semantic.data?.hits.length ?? 0)} passages`}
              {took !== undefined ? ` in ${took} ms` : ""}
            </p>
            {mode === "symbols" && symbols.data ? <SymbolResults data={symbols.data} workspace={slug} /> : null}
            {mode === "text" && textual.data ? <TextResults data={textual.data} workspace={slug} /> : null}
            {mode === "semantic" && semantic.data ? <SemanticResults data={semantic.data} workspace={slug} /> : null}
          </>
        )}
      </div>
    </PageBody>
  );
}

export function SearchView() {
  return (
    <Suspense>
      <SearchBody />
    </Suspense>
  );
}
