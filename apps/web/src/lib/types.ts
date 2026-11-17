/** The API's shapes. Field names are the wire names (snake_case), so nothing is renamed twice. */

export type Role = "owner" | "maintainer" | "developer" | "viewer";

export type User = {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type WorkspaceSummary = {
  id: string;
  slug: string;
  name: string;
  role: Role;
  repository_count: number;
  member_count: number;
};

export type Me = { user: User; workspaces: WorkspaceSummary[] };

export type SessionOut = { user: User; token: string; expires_at: string };

export type WorkspaceSettings = {
  require_independent_review: boolean;
  agent_mode: "auto" | "local";
  run_baseline_tests: boolean;
};

export type Workspace = {
  id: string;
  slug: string;
  name: string;
  description: string;
  settings: WorkspaceSettings;
  role: Role;
  created_at: string;
};

export type Member = {
  user_id: string;
  email: string;
  name: string;
  role: Role;
  joined_at: string;
};

export type MemberAdded = { member: Member; temporary_password: string | null };

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  role: "viewer" | "developer";
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

export type ApiKeyCreated = ApiKey & { key: string };

export type AuditEvent = {
  id: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  actor_name: string | null;
  created_at: string;
};

export type EngineInfo = {
  label: string;
  provider: string;
  model: string | null;
  uses_model: boolean;
};

export type SystemInfo = {
  product_name: string;
  version: string;
  answerer: EngineInfo;
  planner: EngineInfo;
  skills: string[];
  helpers: string[];
  embeddings: string;
  embedding_dim: number;
  sandbox: {
    backend: string;
    image: string | null;
    timeout_s: number;
    memory_mb: number;
    cpus: number;
    network: string;
  };
  max_archive_mb: number;
  allow_signup: boolean;
  needs_setup: boolean;
};

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

// Repositories and the index

export type IndexStatus = "queued" | "indexing" | "ready" | "failed";

export type Snapshot = {
  id: string;
  status: IndexStatus;
  origin: string;
  upload_name: string | null;
  commit_sha: string | null;
  branch: string | null;
  stats: Record<string, number>;
  warnings: { path: string; message: string }[];
  error: string | null;
  created_at: string;
  indexed_at: string | null;
};

export type LanguageStat = { files: number; lines: number; bytes: number };

export type Repository = {
  id: string;
  slug: string;
  name: string;
  description: string;
  source: "git" | "archive";
  git_url: string | null;
  default_branch: string | null;
  status: IndexStatus;
  error: string | null;
  languages: Record<string, LanguageStat>;
  file_count: number;
  symbol_count: number;
  line_count: number;
  size_bytes: number;
  last_indexed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RepositorySettings = {
  test_command: string | null;
  test_timeout_s: number | null;
  memory_mb: number | null;
};

export type RepositoryDetail = Repository & {
  settings: RepositorySettings;
  current_snapshot: Snapshot | null;
  latest_snapshot: Snapshot | null;
  readme_path: string | null;
};

export type FileEntry = {
  path: string;
  language: string;
  size_bytes: number;
  line_count: number;
  is_test: boolean;
  symbol_count: number;
  indexed: boolean;
};

export type FileList = { snapshot_id: string; commit_sha: string | null; files: FileEntry[] };

/** One highlighted run: [class, text]. */
export type Token = [string, string];
export type CodeLine = Token[];

export type OutlineSymbol = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  start_line: number;
  end_line: number;
  signature: string;
  doc: string;
  depth: number;
  ref_count: number;
};

export type Blob = {
  path: string;
  language: string;
  size_bytes: number;
  line_count: number;
  is_test: boolean;
  indexed: boolean;
  parse_error: string | null;
  commit_sha: string | null;
  lines: CodeLine[];
  outline: OutlineSymbol[];
};

export type Edge = {
  symbol_id: string | null;
  name: string;
  kind: string;
  path: string;
  line: number;
  is_test: boolean;
};

export type SymbolDetail = {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  path: string;
  language: string;
  start_line: number;
  end_line: number;
  signature: string;
  doc: string;
  ref_count: number;
  code: CodeLine[];
  callers: Edge[];
  callees: Edge[];
  importers: Edge[];
  tests: Edge[];
};

// Search

export type SymbolHit = {
  id: string;
  repository: string;
  name: string;
  qualified_name: string;
  kind: string;
  path: string;
  language: string;
  start_line: number;
  end_line: number;
  signature: string;
  doc: string;
  ref_count: number;
  is_test: boolean;
};

export type SymbolSearch = { query: string; hits: SymbolHit[]; took_ms: number };

export type LineMatch = { line: number; text: string; ranges: [number, number][] };
export type FileMatch = { repository: string; path: string; language: string; matches: LineMatch[] };
export type TextSearch = {
  query: string;
  regex: boolean;
  files: FileMatch[];
  match_count: number;
  truncated: boolean;
  took_ms: number;
};

export type SemanticHit = {
  repository: string;
  path: string;
  language: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  kind: string | null;
  snippet: string;
  score: number;
  vector_score: number | null;
  keyword_score: number | null;
};
export type SemanticSearch = { query: string; hits: SemanticHit[]; took_ms: number };

export type SearchMode = "symbols" | "text" | "semantic";

// Answers

export type Conversation = {
  id: string;
  title: string;
  repository_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type Source = {
  n: number;
  repository_id: string;
  repository: string;
  file_id: string;
  path: string;
  language: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  symbol_kind: string | null;
  snippet: string;
  score: number;
};

export type Citation = {
  n: number;
  repository_id: string;
  repository: string;
  file_id: string;
  path: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  snippet: string;
};

export type AnswerUsage = {
  answerer: string;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  sources: Source[];
  usage: AnswerUsage | null;
  created_at: string;
};

export type Answer = { conversation_id: string | null; message: Message };

// Tasks, patches, runs

export type TaskStatus =
  "queued" | "running" | "awaiting_review" | "approved" | "applying" | "applied" | "rejected" | "failed" | "cancelled";

export type PatchStatus = "proposed" | "approved" | "rejected" | "superseded" | "applying" | "applied";

export type RunStatus = "queued" | "running" | "passed" | "failed" | "error" | "timed_out" | "cancelled";

export type TraceEvent = { at: string; message: string; kind: string };

export type RunSummary = {
  id: string;
  number: number;
  trigger: string;
  status: RunStatus;
  total: number;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  duration_ms: number | null;
  backend: string | null;
  created_at: string;
};

export type FileStat = { path: string; change_type: string; additions: number; deletions: number };

export type PatchSummary = {
  id: string;
  revision: number;
  status: PatchStatus;
  summary: string;
  additions: number;
  deletions: number;
  files: FileStat[];
  planner: string;
  skill: string;
  created_at: string;
  decided_at: string | null;
  applied_branch: string | null;
  applied_commit: string | null;
};

export type Task = {
  id: string;
  number: number;
  repository_id: string;
  repository: string;
  title: string;
  status: TaskStatus;
  skill: string | null;
  planner: string | null;
  requested_by: string | null;
  patch_count: number;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskDetail = Task & {
  description: string;
  base_commit: string | null;
  error_code: string | null;
  trace: TraceEvent[];
  usage: Record<string, number>;
  started_at: string | null;
  finished_at: string | null;
  patches: PatchSummary[];
  runs: RunSummary[];
  can_approve: boolean;
};

export type DiffLine = {
  kind: "context" | "add" | "del";
  old_line: number | null;
  new_line: number | null;
  tokens: Token[];
};

export type Hunk = {
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  section: string;
  lines: DiffLine[];
};

export type PatchFile = {
  path: string;
  change_type: string;
  language: string;
  additions: number;
  deletions: number;
  hunks: Hunk[];
};

export type ReviewComment = {
  id: string;
  author: string | null;
  author_id: string | null;
  body: string;
  path: string | null;
  line: number | null;
  side: "old" | "new" | null;
  resolved: boolean;
  created_at: string;
};

export type PlanStep = { title: string; detail: string };

export type Patch = PatchSummary & {
  task_id: string;
  task_number: number;
  rationale: string;
  plan: PlanStep[];
  base_commit: string | null;
  decision_note: string | null;
  decided_by: string | null;
  applied_at: string | null;
  apply_error: string | null;
  diff_files: PatchFile[];
  comments: ReviewComment[];
  baseline_run: RunSummary | null;
  verify_run: RunSummary | null;
};

export type TestRun = RunSummary & {
  repository_id: string;
  repository: string;
  task_number: number | null;
  patch_id: string | null;
  commit_sha: string | null;
  command: string;
  image: string | null;
  exit_code: number | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type TestCase = {
  name: string;
  classname: string;
  status: string;
  duration_ms: number;
  message: string;
  file: string | null;
  line: number | null;
};

export type TestRunDetail = TestRun & {
  limits: Record<string, number | string>;
  results: TestCase[];
  log_tail: string;
  log_truncated: boolean;
  has_full_log: boolean;
};

// Overview

export type Overview = {
  days: number;
  workspace_id: string;
  totals: {
    repositories: number;
    repositories_ready: number;
    files: number;
    symbols: number;
    lines: number;
    open_reviews: number;
    tasks: number;
    tasks_applied: number;
    tasks_failed: number;
    approval_rate: number;
    test_runs: number;
    test_pass_rate: number;
    median_run_ms: number;
    questions: number;
    searches: number;
    model_tokens: number;
    median_review_hours: number | null;
  };
  daily: { day: string; runs_passed: number; runs_failed: number; questions: number; searches: number }[];
  tasks_by_status: { status: string; count: number }[];
  recent: {
    kind: string;
    title: string;
    detail: string;
    status: string;
    href: string;
    at: string;
    actor: string | null;
  }[];
};
