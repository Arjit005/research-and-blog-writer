/**
 * Enterprise typed API client for AI Research & Visual Blog Studio.
 * Uses native fetch with credentials: 'include' for HttpOnly cookies.
 */

export interface User {
  id: number;
  email: string;
}

export interface ArticleSummary {
  id: number;
  topic: string;
  word_count: number;
  tone?: string;
  audience?: string;
  created_at: string;
}

export interface ArticleDetail extends ArticleSummary {
  content: string;
  target_length?: string;
  generation_time_sec?: number;
  tokens_used?: number;
}

export interface RunResponse {
  run_id: string;
  status: string;
  topic: string;
}

export interface RunStatus {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  topic: string;
  result_article_id?: number | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RevisionSummary {
  id: number;
  revision_num: number;
  summary: string;
  created_at: string;
  author?: string;
}

export interface DiffResult {
  article_id: number;
  from_revision: number;
  to_revision: number;
  diff_patch: string;
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    let errMessage = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) errMessage = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      else if (body.error?.message) errMessage = body.error.message;
    } catch {
      // ignore
    }
    throw new Error(errMessage);
  }

  return res.json() as Promise<T>;
}

export const api = {
  // Auth
  async requestOtp(email: string): Promise<{ success: boolean; message: string; dev_code?: string }> {
    return fetchJson("/api/v1/auth/otp/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  async verifyOtp(email: string, code: string): Promise<{ success: boolean; message: string; user?: User; token?: string }> {
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
  async listArticles(): Promise<ArticleSummary[]> {
    return fetchJson("/api/v1/articles");
  },

  async getArticle(id: number): Promise<ArticleDetail> {
    return fetchJson(`/api/v1/articles/${id}`);
  },

  async deleteArticle(id: number): Promise<{ success: boolean }> {
    return fetchJson(`/api/v1/articles/${id}`, { method: "DELETE" });
  },

  // Research Runs
  async createRun(data: {
    topic: string;
    tone?: string;
    audience?: string;
    target_length?: string;
  }): Promise<RunResponse> {
    return fetchJson("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getRun(runId: string): Promise<RunStatus> {
    return fetchJson(`/api/v1/runs/${runId}`);
  },

  async cancelRun(runId: string): Promise<{ success: boolean; message: string }> {
    return fetchJson(`/api/v1/runs/${runId}/cancel`, { method: "POST" });
  },

  // Revisions & Diffs
  async listRevisions(articleId: number): Promise<RevisionSummary[]> {
    return fetchJson(`/api/v1/revisions/articles/${articleId}`);
  },

  async getRevisionDiff(articleId: number, fromRev: number, toRev: number): Promise<DiffResult> {
    return fetchJson(`/api/v1/revisions/articles/${articleId}/diff?from_rev=${fromRev}&to_rev=${toRev}`);
  },

  async restoreRevision(articleId: number, revisionId: number): Promise<{ success: boolean; message: string }> {
    return fetchJson(`/api/v1/revisions/articles/${articleId}/restore/${revisionId}`, { method: "POST" });
  },

  // Telemetry & Cache
  async getTelemetryStats(): Promise<any> {
    return fetchJson("/api/v1/telemetry/stats");
  },

  async pruneCache(): Promise<{ success: boolean; pruned_count: number }> {
    return fetchJson("/api/v1/telemetry/cache/prune", { method: "POST" });
  },
};
