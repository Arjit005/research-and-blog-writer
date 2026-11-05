/**
 * Typed API client for the AI Research & Visual Blog Studio.
 *
 * The frontend is built as a static export (`output: "export"`) and, in
 * production, served by the FastAPI backend from the same origin, so relative
 * `/api/v1/...` URLs are correct there.
 *
 * During `next dev` the UI runs on :3000 while FastAPI runs on :8000, so a
 * relative URL would 404. Set `NEXT_PUBLIC_API_BASE=http://localhost:8000`
 * before `npm run dev` (see frontend/README.md). The value is inlined at build
 * time, so production builds should leave it unset to keep same-origin paths.
 *
 * Note: Next.js rewrites are not available with `output: "export"`, so this
 * env-var indirection is the supported dev proxy mechanism.
 */

const RAW_API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
export const API_BASE = RAW_API_BASE.replace(/\/+$/, "");

/** Resolve an API path against the configured base (empty string = same origin). */
export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}

const DEFAULT_TIMEOUT_MS = 30_000;

export interface User {
  id: number;
  email: string;
}

export interface AuthResult {
  success: boolean;
  message: string;
  user?: User;
  token?: string;
  dev_code?: string;
}

export interface ArticleSummary {
  id: number;
  topic: string;
  word_count: number;
  tone?: string;
  audience?: string;
  created_at: string;
}

export interface ArticleListResponse {
  items: ArticleSummary[];
  total: number;
  limit: number;
  next_cursor?: number | null;
}

export interface ArticleDetail extends ArticleSummary {
  content: string;
  target_length?: string;
  generation_time_sec?: number;
  tokens_used?: number;
  updated_at?: string;
  user_id?: number;
}

export interface RunResponse {
  run_id: string;
  status: string;
  topic: string;
}

export type RunState = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface RunStatus {
  run_id: string;
  status: RunState;
  topic: string;
  result_article_id?: number | null;
  error_message?: string | null;
  trace_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RevisionSummary {
  id: number;
  revision_num: number;
  summary: string;
  created_at: string;
}

export interface DiffStats {
  additions: number;
  deletions: number;
  total_changes: number;
}

/**
 * Mirrors `DiffResponse` from `backend/routes/revisions.py`.
 * `diff_html` is server-generated, HTML-escaped markup; the client never
 * injects it as raw HTML (see components/diff-viewer.tsx).
 */
export interface DiffResult {
  article_id?: number;
  from_revision: number;
  to_revision: number;
  diff_html: string;
  stats: DiffStats;
}

export interface CopilotEditResult {
  success: boolean;
  new_revision_num: number;
  content: string;
}

export interface CacheMetrics {
  total_hits?: number;
  l1_hits?: number;
  l2_hits?: number;
  [key: string]: unknown;
}

export interface TelemetryStats {
  studio: Record<string, unknown>;
  cache: {
    metrics: CacheMetrics;
    db_stats: Record<string, unknown>;
  };
  database: {
    backend: string;
    is_live: boolean;
    status_message: string;
  };
  recent_runs: Array<Record<string, unknown>>;
}

export interface UserKeysInfo {
  has_gemini: boolean;
  has_openrouter: boolean;
  has_beatapi?: boolean;
  gemini_masked?: string | null;
  openrouter_masked?: string | null;
  beatapi_masked?: string | null;
  server_has_gemini: boolean;
  server_has_openrouter: boolean;
  server_has_beatapi?: boolean;
}

export interface UserKeysUpdate {
  gemini_api_key?: string;
  openrouter_api_key?: string;
  beatapi_key?: string;
}

interface RawDiffResponse {
  old_revision_num: number;
  new_revision_num: number;
  diff_html: string;
  stats?: Partial<DiffStats>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Human-readable message from a FastAPI/standard error payload. */
export function extractApiErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) return fallback;

  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (detail !== undefined) return JSON.stringify(detail);

  const error = payload.error;
  if (isRecord(error) && typeof error.message === "string") return error.message;

  return fallback;
}

/** Human-readable message from an unknown thrown value. */
export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error) return error;
  return fallback;
}

async function fetchJson<T>(path: string, options: RequestInit = {}, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const callerSignal = options.signal;
  const onCallerAbort = () => controller.abort();
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort();
    else callerSignal.addEventListener("abort", onCallerAbort);
  }

  try {
    const res = await fetch(apiUrl(path), {
      ...options,
      credentials: "include",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
    });

    if (!res.ok) {
      let message = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const body: unknown = await res.json();
        message = extractApiErrorMessage(body, message);
      } catch {
        // Non-JSON error body; keep the status line.
      }
      throw new Error(message);
    }

    return (await res.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s. The backend may be unreachable.`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
    callerSignal?.removeEventListener("abort", onCallerAbort);
  }
}

export const api = {
  // Auth
  async loginWithGoogle(idToken: string): Promise<AuthResult> {
    return fetchJson("/api/v1/auth/google", {
      method: "POST",
      body: JSON.stringify({ id_token: idToken }),
    });
  },

  async loginWithPassword(email: string, password: string, otpCode?: string): Promise<AuthResult> {
    return fetchJson("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, otp_code: otpCode || null }),
    });
  },

  async requestOtp(email: string): Promise<AuthResult> {
    return fetchJson("/api/v1/auth/otp/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  async verifyOtp(email: string, code: string): Promise<AuthResult> {
    return fetchJson("/api/v1/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify({ email, code }),
    });
  },

  async getMe(): Promise<User> {
    return fetchJson("/api/v1/auth/me");
  },

  async logout(): Promise<{ success: boolean }> {
    return fetchJson("/api/v1/auth/logout", { method: "POST" });
  },

  // Articles
  async listArticles(limit: number = 20, cursor?: number): Promise<ArticleSummary[]> {
    const query = new URLSearchParams();
    if (limit) query.set("limit", String(limit));
    if (cursor) query.set("cursor", String(cursor));
    const qs = query.toString() ? `?${query.toString()}` : "";
    const res = await fetchJson<ArticleSummary[] | ArticleListResponse>(`/api/v1/articles${qs}`);
    if (Array.isArray(res)) {
      return res;
    }
    if (res && typeof res === "object" && Array.isArray((res as ArticleListResponse).items)) {
      return (res as ArticleListResponse).items;
    }
    return [];
  },

  async getArticle(id: number): Promise<ArticleDetail> {
    return fetchJson(`/api/v1/articles/${id}`);
  },

  // Research Runs
  async startRun(params: {
    topic: string;
    tone?: string;
    audience?: string;
    target_length?: string;
  }): Promise<RunResponse> {
    return fetchJson("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify(params),
    });
  },

  async createRun(params: {
    topic: string;
    tone?: string;
    audience?: string;
    target_length?: string;
  }): Promise<RunResponse> {
    return this.startRun(params);
  },

  async getRunStatus(runId: string): Promise<RunStatus> {
    return fetchJson(`/api/v1/runs/${runId}`);
  },

  async cancelRun(runId: string): Promise<{ success: boolean; message: string }> {
    return fetchJson(`/api/v1/runs/${runId}/cancel`, { method: "POST" });
  },

  // Revisions & Diffs
  async listRevisions(articleId: number): Promise<RevisionSummary[]> {
    return fetchJson(`/api/v1/articles/${articleId}/revisions`);
  },

  /**
   * Backend returns `{ old_revision_num, new_revision_num, diff_html, stats }`.
   * `diff_html` is escaped server-generated markup rendered through the safe
   * allowlist renderer in components/diff-viewer.tsx (never raw innerHTML).
   */
  async getDiff(articleId: number, fromRev: number, toRev: number): Promise<DiffResult> {
    const raw = await fetchJson<RawDiffResponse>(`/api/v1/articles/${articleId}/revisions/diff/${fromRev}/${toRev}`);
    const from = raw.old_revision_num ?? fromRev;
    const to = raw.new_revision_num ?? toRev;
    return {
      article_id: articleId,
      from_revision: from,
      to_revision: to,
      diff_html: raw.diff_html ?? "",
      stats: {
        additions: raw.stats?.additions ?? 0,
        deletions: raw.stats?.deletions ?? 0,
        total_changes: raw.stats?.total_changes ?? 0,
      },
    };
  },

  async getRevisionDiff(articleId: number, fromRev: number, toRev: number): Promise<DiffResult> {
    return this.getDiff(articleId, fromRev, toRev);
  },

  async restoreRevision(articleId: number, revisionNum: number): Promise<{ success: boolean; message: string }> {
    return fetchJson(`/api/v1/articles/${articleId}/revisions/${revisionNum}/restore`, {
      method: "POST",
    });
  },

  /**
   * Backend contract: POST /api/v1/articles/{article_id}/edit
   * Request: { "instruction": string }
   * Response: { "success": boolean, "new_revision_num": number, "content": string }
   */
  async applyCopilotEdit(params: {
    article_id: number;
    instruction: string;
  }): Promise<CopilotEditResult> {
    return fetchJson(`/api/v1/articles/${params.article_id}/edit`, {
      method: "POST",
      body: JSON.stringify({ instruction: params.instruction }),
      // AI edits can take longer than plain CRUD calls.
    }, 120_000);
  },

  // Telemetry
  async getTelemetryStats(): Promise<TelemetryStats> {
    return fetchJson("/api/v1/telemetry/stats");
  },

  async getTelemetry(): Promise<TelemetryStats> {
    return this.getTelemetryStats();
  },

  // API Keys Management
  async getUserKeys(): Promise<UserKeysInfo> {
    return fetchJson("/api/v1/auth/keys");
  },

  async saveUserKeys(data: UserKeysUpdate): Promise<{ status: string; message: string }> {
    return fetchJson("/api/v1/auth/keys", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
};
