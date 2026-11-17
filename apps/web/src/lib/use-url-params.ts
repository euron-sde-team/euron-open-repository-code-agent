"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { mergeParams, type ParamUpdates } from "@/lib/url-params";

/**
 * Filter and page state that lives in the URL, so a view can be shared, bookmarked and
 * crawled (`?category=fact&user_id=amelia.novak&offset=50`). Updates replace the history
 * entry instead of adding one per keystroke. Changing a filter should reset `offset`:
 * `update({ category: ["fact"], offset: null })`.
 *
 * `useSearchParams` needs a Suspense boundary above the component that calls this hook
 * (Next.js requirement for pages that are prerendered): wrap the page body in `<Suspense>`.
 */
export function useUrlParams(): {
  params: URLSearchParams;
  get: (key: string) => string | null;
  getAll: (key: string) => string[];
  update: (updates: ParamUpdates) => void;
} {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const update = useCallback(
    (updates: ParamUpdates) => {
      const query = mergeParams(new URLSearchParams(window.location.search), updates);
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [router, pathname],
  );
  return {
    params,
    get: (key) => params.get(key),
    getAll: (key) => params.getAll(key),
    update,
  };
}
