/**
 * Where to go after signing in. Only same-origin paths are honoured: "//evil.example" and
 * "https://evil.example" would turn the sign-in page into an open redirect.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return "/";
  return raw;
}

/** `/w/<workspace>/<segments...>`; the workspace slug is encoded, segments are joined as given. */
export function wsPath(workspace: string, ...segments: string[]): string {
  const base = `/w/${encodeURIComponent(workspace)}`;
  const rest = segments.filter(Boolean).join("/");
  return rest ? `${base}/${rest}` : base;
}

/** A file path as URL segments: each segment is encoded, the slashes stay. */
export function encodePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

/** The code view of a file, optionally at a line or a range (`#L12-L30`). */
export function codePath(workspace: string, repository: string, path: string, start?: number, end?: number): string {
  const base = wsPath(workspace, "repos", encodeURIComponent(repository), "code", encodePath(path));
  if (!start) return base;
  return end && end !== start ? `${base}#L${start}-L${end}` : `${base}#L${start}`;
}

/** The line range a hash like `#L12` or `#L12-L30` points at. */
export function parseLineHash(hash: string): { start: number; end: number } | null {
  const match = /^#?L(\d+)(?:-L?(\d+))?$/.exec(hash);
  if (!match) return null;
  const start = Number(match[1]);
  const end = match[2] ? Number(match[2]) : start;
  if (start < 1) return null;
  return { start: Math.min(start, end), end: Math.max(start, end) };
}
