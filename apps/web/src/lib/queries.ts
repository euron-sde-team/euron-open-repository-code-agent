"use client";

/**
 * Data access for the whole dashboard: one TanStack Query hook per API endpoint.
 *
 * CONVENTIONS
 *
 * Layout. Pages live in `app/w/[workspace]/<route>/page.tsx` and stay thin; feature UI goes
 * in `components/<area>/`. Shared building blocks are `components/ui/*` (primitives) and
 * `components/domain/*` (status badges, code rendering). Design tokens are CSS variables in
 * `app/globals.css`; use the Tailwind names (`bg-card`, `text-muted-foreground`,
 * `text-hl-kw`), never raw colours.
 *
 * The active workspace. Inside `app/w/[workspace]/*` call `useActiveWorkspace()` for the
 * slug and the role, and `useCan("developer")` to hide controls the caller may not use. The
 * API enforces the same rules; the UI only avoids offering what would be refused.
 *
 * Keys. `qk` builds every query key; the workspace slug is always the second element, so
 * `invalidateQueries({ queryKey: ["tasks", workspace] })` refreshes every task list.
 *
 * Polling. Lists and details that can still change (a repository being indexed, a task
 * running, a test run in the sandbox) refetch every two seconds while something is
 * unfinished, and stop once everything has settled.
 *
 * Writes. A mutation hook returns the `useMutation` result: call `mutateAsync` in a handler.
 * Success toasts belong to the call site. Failures are toasted for you by the QueryClient's
 * mutation cache (see `lib/providers.tsx`); pass `{ silent: true }` when the form renders
 * `mutation.error` inline.
 */

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, toQuery, ws } from "@/lib/api";
import { ACTIVE_INDEX, ACTIVE_RUN, ACTIVE_TASK } from "@/lib/labels";
import type {
  ApiKey,
  ApiKeyCreated,
  AuditEvent,
  Blob,
  Conversation,
  FileList,
  Me,
  Member,
  MemberAdded,
  Message,
  Overview,
  Page,
  Patch,
  ReviewComment,
  Repository,
  RepositoryDetail,
  RepositorySettings,
  Role,
  SemanticSearch,
  SessionOut,
  Snapshot,
  SymbolDetail,
  SymbolSearch,
  SystemInfo,
  Task,
  TaskDetail,
  TestRun,
  TestRunDetail,
  TextSearch,
  User,
  Workspace,
  WorkspaceSettings,
} from "@/lib/types";

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: { silent?: boolean };
  }
}

/** Pass `{ silent: true }` when the form shows the error itself. */
export type HookOptions = { silent?: boolean };

const meta = (options?: HookOptions) => ({ silent: options?.silent ?? false });

const POLL_MS = 2000;

export type PageParams = { limit?: number; offset?: number };
export type RepositoryParams = PageParams & { q?: string; status?: string };
export type TaskParams = PageParams & { status?: string; repository?: string; q?: string };
export type RunParams = PageParams & {
  repository?: string;
  task?: number;
  status?: string;
  trigger?: string;
};
export type TextParams = {
  q: string;
  regex?: boolean;
  case_sensitive?: boolean;
  repository?: string;
  path?: string;
  language?: string;
};
export type SymbolParams = { q: string; repository?: string; kind?: string };
export type SemanticParams = { q: string; repository?: string };

export const qk = {
  system: ["system"] as const,
  me: ["me"] as const,
  workspace: (w: string) => ["workspace", w] as const,
  overview: (w: string, days: number) => ["overview", w, days] as const,
  members: (w: string) => ["members", w] as const,
  apiKeys: (w: string) => ["api-keys", w] as const,
  audit: (w: string, params: PageParams) => ["audit", w, params] as const,
  repositories: (w: string, params: RepositoryParams = {}) => ["repositories", w, params] as const,
  repository: (w: string, repo: string) => ["repository", w, repo] as const,
  snapshots: (w: string, repo: string) => ["snapshots", w, repo] as const,
  files: (w: string, repo: string) => ["files", w, repo] as const,
  blob: (w: string, repo: string, path: string) => ["blob", w, repo, path] as const,
  symbol: (w: string, id: string) => ["symbol", w, id] as const,
  searchSymbols: (w: string, p: SymbolParams) => ["search-symbols", w, p] as const,
  searchText: (w: string, p: TextParams) => ["search-text", w, p] as const,
  searchSemantic: (w: string, p: SemanticParams) => ["search-semantic", w, p] as const,
  conversations: (w: string) => ["conversations", w] as const,
  messages: (w: string, id: string) => ["messages", w, id] as const,
  tasks: (w: string, params: TaskParams = {}) => ["tasks", w, params] as const,
  task: (w: string, number: number | string) => ["task", w, String(number)] as const,
  patch: (w: string, id: string) => ["patch", w, id] as const,
  runs: (w: string, params: RunParams = {}) => ["runs", w, params] as const,
  run: (w: string, ref: number | string) => ["run", w, String(ref)] as const,
  runLog: (w: string, ref: number | string) => ["run-log", w, String(ref)] as const,
};

/** Everything a change to tasks, patches or runs can alter. */
export function invalidateWork(client: QueryClient, workspace: string): Promise<void> {
  const keys = ["tasks", "task", "patch", "runs", "run", "run-log", "overview"];
  return Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: [key, workspace] }))).then(() => undefined);
}

/** Everything a change to repositories or their index can alter. */
export function invalidateIndex(client: QueryClient, workspace: string): Promise<void> {
  const keys = [
    "repositories",
    "repository",
    "snapshots",
    "files",
    "blob",
    "symbol",
    "search-symbols",
    "search-text",
    "search-semantic",
    "overview",
  ];
  return Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: [key, workspace] }))).then(() => undefined);
}

// Accounts and sessions -------------------------------------------------------------------

export function useSystemInfo() {
  return useQuery({
    queryKey: qk.system,
    queryFn: () => api<SystemInfo>("/api/v1/system/info"),
    staleTime: 300_000,
  });
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: qk.me,
    queryFn: () => api<Me>("/api/v1/auth/me"),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { email: string; password: string }) =>
      api<SessionOut>("/api/v1/auth/login", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useSignup(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { email: string; name: string; password: string }) =>
      api<SessionOut>("/api/v1/auth/signup", { method: "POST", json: body }),
    onSuccess: () =>
      Promise.all([client.invalidateQueries({ queryKey: qk.me }), client.invalidateQueries({ queryKey: qk.system })]),
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: () => api<void>("/api/v1/auth/logout", { method: "POST" }),
    onSettled: () => client.clear(),
  });
}

export function useChangePassword(options?: HookOptions) {
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api<SessionOut>("/api/v1/auth/password", { method: "POST", json: body }),
  });
}

export function useUpdateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) => api<User>("/api/v1/auth/me", { method: "PATCH", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

// Workspaces ------------------------------------------------------------------------------

export function useWorkspace(workspace: string, enabled = true) {
  return useQuery({
    queryKey: qk.workspace(workspace),
    queryFn: () => api<Workspace>(ws(workspace)),
    enabled,
  });
}

export function useCreateWorkspace(options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { name: string; description?: string }) =>
      api<Workspace>("/api/v1/workspaces", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useUpdateWorkspace(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string; description?: string; settings?: WorkspaceSettings }) =>
      api<Workspace>(ws(workspace), { method: "PATCH", json: body }),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: qk.workspace(workspace) }),
        client.invalidateQueries({ queryKey: qk.me }),
      ]),
  });
}

export function useOverview(workspace: string, days = 14) {
  return useQuery({
    queryKey: qk.overview(workspace, days),
    queryFn: () => api<Overview>(`${ws(workspace)}/overview${toQuery({ days })}`),
    refetchInterval: 30_000,
  });
}

export function useMembers(workspace: string, enabled = true) {
  return useQuery({
    queryKey: qk.members(workspace),
    queryFn: () => api<Member[]>(`${ws(workspace)}/members`),
    enabled,
  });
}

export function useAddMember(workspace: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { email: string; name?: string; role: Role }) =>
      api<MemberAdded>(`${ws(workspace)}/members`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.members(workspace) }),
  });
}

export function useChangeMemberRole(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { userId: string; role: Role }) =>
      api<{ ok: boolean }>(`${ws(workspace)}/members/${v.userId}`, {
        method: "PATCH",
        json: { role: v.role },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.members(workspace) }),
  });
}

export function useRemoveMember(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api<void>(`${ws(workspace)}/members/${userId}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.members(workspace) }),
  });
}

export function useApiKeys(workspace: string, enabled = true) {
  return useQuery({
    queryKey: qk.apiKeys(workspace),
    queryFn: () => api<ApiKey[]>(`${ws(workspace)}/api-keys`),
    enabled,
  });
}

export function useCreateApiKey(workspace: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { name: string; role: "viewer" | "developer"; expires_in_days?: number }) =>
      api<ApiKeyCreated>(`${ws(workspace)}/api-keys`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.apiKeys(workspace) }),
  });
}

export function useRevokeApiKey(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`${ws(workspace)}/api-keys/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.apiKeys(workspace) }),
  });
}

export function useAudit(workspace: string, params: PageParams, enabled = true) {
  return useQuery({
    queryKey: qk.audit(workspace, params),
    queryFn: () => api<AuditEvent[]>(`${ws(workspace)}/audit${toQuery(params)}`),
    placeholderData: keepPreviousData,
    enabled,
  });
}

// Repositories ----------------------------------------------------------------------------

export function useRepositories(workspace: string, params: RepositoryParams = {}) {
  return useQuery({
    queryKey: qk.repositories(workspace, params),
    queryFn: () => api<Page<Repository>>(`${ws(workspace)}/repositories${toQuery(params)}`),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((r) => ACTIVE_INDEX.has(r.status)) ? POLL_MS : false),
  });
}

export function useRepository(workspace: string, repo: string) {
  return useQuery({
    queryKey: qk.repository(workspace, repo),
    queryFn: () => api<RepositoryDetail>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}`),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && (ACTIVE_INDEX.has(data.status) || ACTIVE_INDEX.has(data.latest_snapshot?.status ?? "ready"))
        ? POLL_MS
        : false;
    },
  });
}

export function useConnectRepository(workspace: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { git_url: string; branch?: string; name?: string; description?: string }) =>
      api<Repository>(`${ws(workspace)}/repositories`, { method: "POST", json: body }),
    onSuccess: () => invalidateIndex(client, workspace),
  });
}

export function useUploadRepository(workspace: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (v: { file: File; name?: string; description?: string }) => {
      const form = new FormData();
      form.append("file", v.file);
      if (v.name) form.append("name", v.name);
      if (v.description) form.append("description", v.description);
      return api<Repository>(`${ws(workspace)}/repositories/upload`, { method: "POST", body: form });
    },
    onSuccess: () => invalidateIndex(client, workspace),
  });
}

export function useUploadVersion(workspace: string, repo: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<Snapshot>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}/upload`, {
        method: "POST",
        body: form,
      });
    },
    onSuccess: () => invalidateIndex(client, workspace),
  });
}

export function useSyncRepository(workspace: string, repo: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<Snapshot>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}/sync`, { method: "POST" }),
    onSuccess: () => invalidateIndex(client, workspace),
  });
}

export function useUpdateRepository(workspace: string, repo: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string; description?: string; settings?: RepositorySettings }) =>
      api<RepositoryDetail>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}`, {
        method: "PATCH",
        json: body,
      }),
    onSuccess: () => invalidateIndex(client, workspace),
  });
}

export function useDeleteRepository(workspace: string, repo: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}`, { method: "DELETE" }),
    onSuccess: () => invalidateIndex(client, workspace),
  });
}

export function useSnapshots(workspace: string, repo: string) {
  return useQuery({
    queryKey: qk.snapshots(workspace, repo),
    queryFn: () => api<Snapshot[]>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}/snapshots`),
  });
}

export function useFiles(workspace: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: qk.files(workspace, repo),
    queryFn: () => api<FileList>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}/files`),
    enabled,
    staleTime: 60_000,
  });
}

export function useBlob(workspace: string, repo: string, path: string, enabled = true) {
  return useQuery({
    queryKey: qk.blob(workspace, repo, path),
    queryFn: () =>
      api<Blob>(
        `${ws(workspace)}/repositories/${encodeURIComponent(repo)}/blob/${path
          .split("/")
          .map(encodeURIComponent)
          .join("/")}`,
      ),
    enabled,
    staleTime: 60_000,
  });
}

export function useSymbol(workspace: string, id: string | null) {
  return useQuery({
    queryKey: qk.symbol(workspace, id ?? ""),
    queryFn: () => api<SymbolDetail>(`${ws(workspace)}/symbols/${id}`),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

// Search ----------------------------------------------------------------------------------

export function useSymbolSearch(workspace: string, params: SymbolParams) {
  return useQuery({
    queryKey: qk.searchSymbols(workspace, params),
    queryFn: () => api<SymbolSearch>(`${ws(workspace)}/search/symbols${toQuery({ ...params, limit: 40 })}`),
    enabled: params.q.trim().length > 0,
    placeholderData: keepPreviousData,
  });
}

export function useTextSearch(workspace: string, params: TextParams) {
  return useQuery({
    queryKey: qk.searchText(workspace, params),
    queryFn: () => api<TextSearch>(`${ws(workspace)}/search/text${toQuery(params)}`),
    enabled: params.q.trim().length >= 2,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useSemanticSearch(workspace: string, params: SemanticParams) {
  return useQuery({
    queryKey: qk.searchSemantic(workspace, params),
    queryFn: () => api<SemanticSearch>(`${ws(workspace)}/search/semantic${toQuery({ ...params, limit: 12 })}`),
    enabled: params.q.trim().length > 0,
    placeholderData: keepPreviousData,
  });
}

// Conversations ---------------------------------------------------------------------------

export function useConversations(workspace: string) {
  return useQuery({
    queryKey: qk.conversations(workspace),
    queryFn: () => api<Conversation[]>(`${ws(workspace)}/conversations${toQuery({ limit: 50 })}`),
  });
}

export function useMessages(workspace: string, id: string | null) {
  return useQuery({
    queryKey: qk.messages(workspace, id ?? ""),
    queryFn: () => api<Message[]>(`${ws(workspace)}/conversations/${id}/messages`),
    enabled: Boolean(id),
    staleTime: Infinity,
  });
}

export function useCreateConversation(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { repository?: string; title?: string }) =>
      api<Conversation>(`${ws(workspace)}/conversations`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.conversations(workspace) }),
  });
}

export function useRenameConversation(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; title: string }) =>
      api<Conversation>(`${ws(workspace)}/conversations/${v.id}`, { method: "PATCH", json: { title: v.title } }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.conversations(workspace) }),
  });
}

export function useDeleteConversation(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`${ws(workspace)}/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.conversations(workspace) }),
  });
}

// Tasks, patches, runs --------------------------------------------------------------------

export function useTasks(workspace: string, params: TaskParams = {}) {
  return useQuery({
    queryKey: qk.tasks(workspace, params),
    queryFn: () => api<Page<Task>>(`${ws(workspace)}/tasks${toQuery(params)}`),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((t) => ACTIVE_TASK.has(t.status)) ? POLL_MS : false),
  });
}

export function useTask(workspace: string, number: number | string) {
  return useQuery({
    queryKey: qk.task(workspace, number),
    queryFn: () => api<TaskDetail>(`${ws(workspace)}/tasks/${number}`),
    refetchInterval: (query) => (query.state.data && ACTIVE_TASK.has(query.state.data.status) ? POLL_MS : false),
  });
}

export function useCreateTask(workspace: string, options?: HookOptions) {
  const client = useQueryClient();
  return useMutation({
    meta: meta(options),
    mutationFn: (body: { repository: string; title: string; description?: string }) =>
      api<Task>(`${ws(workspace)}/tasks`, { method: "POST", json: body }),
    onSuccess: () => invalidateWork(client, workspace),
  });
}

export function useRetryTask(workspace: string, number: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (description?: string) =>
      api<TaskDetail>(`${ws(workspace)}/tasks/${number}/retry`, {
        method: "POST",
        json: description === undefined ? {} : { description },
      }),
    onSuccess: () => invalidateWork(client, workspace),
  });
}

export function useCancelTask(workspace: string, number: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<TaskDetail>(`${ws(workspace)}/tasks/${number}/cancel`, { method: "POST" }),
    onSuccess: () => invalidateWork(client, workspace),
  });
}

export function usePatch(workspace: string, id: string | null) {
  return useQuery({
    queryKey: qk.patch(workspace, id ?? ""),
    queryFn: () => api<Patch>(`${ws(workspace)}/patches/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data && ["applying", "approved"].includes(query.state.data.status) && query.state.data.applied_branch
        ? POLL_MS
        : false,
  });
}

export function useDecidePatch(workspace: string, id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { verb: "approve" | "reject"; note?: string }) =>
      api<Patch>(`${ws(workspace)}/patches/${id}/${v.verb}`, { method: "POST", json: { note: v.note ?? null } }),
    onSuccess: () => invalidateWork(client, workspace),
  });
}

export function useApplyPatch(workspace: string, id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (branch?: string) =>
      api<Patch>(`${ws(workspace)}/patches/${id}/apply`, { method: "POST", json: { branch: branch || null } }),
    onSuccess: () => invalidateWork(client, workspace),
  });
}

export function useTestPatch(workspace: string, id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<TestRun>(`${ws(workspace)}/patches/${id}/test-runs`, { method: "POST" }),
    onSuccess: () => invalidateWork(client, workspace),
  });
}

export function useAddComment(workspace: string, patchId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { body: string; path?: string; line?: number; side?: "old" | "new" }) =>
      api<ReviewComment>(`${ws(workspace)}/patches/${patchId}/comments`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.patch(workspace, patchId) }),
  });
}

export function useUpdateComment(workspace: string, patchId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; resolved?: boolean; body?: string }) =>
      api<ReviewComment>(`${ws(workspace)}/comments/${v.id}`, {
        method: "PATCH",
        json: { resolved: v.resolved, body: v.body },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.patch(workspace, patchId) }),
  });
}

export function useDeleteComment(workspace: string, patchId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`${ws(workspace)}/comments/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.patch(workspace, patchId) }),
  });
}

export function useRuns(workspace: string, params: RunParams = {}) {
  return useQuery({
    queryKey: qk.runs(workspace, params),
    queryFn: () => api<Page<TestRun>>(`${ws(workspace)}/test-runs${toQuery(params)}`),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((r) => ACTIVE_RUN.has(r.status)) ? POLL_MS : false),
  });
}

export function useRun(workspace: string, ref: number | string) {
  return useQuery({
    queryKey: qk.run(workspace, ref),
    queryFn: () => api<TestRunDetail>(`${ws(workspace)}/test-runs/${ref}`),
    refetchInterval: (query) => (query.state.data && ACTIVE_RUN.has(query.state.data.status) ? POLL_MS : false),
  });
}

export function useStartRun(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (repo: string) =>
      api<TestRun>(`${ws(workspace)}/repositories/${encodeURIComponent(repo)}/test-runs`, { method: "POST" }),
    onSuccess: () => invalidateWork(client, workspace),
  });
}
