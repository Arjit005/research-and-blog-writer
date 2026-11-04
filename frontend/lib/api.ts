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
  trace_url?: string | null;
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
  article_id?: number;
  from_revision: number;
  to_revision: number;
  diff_patch: string;
  diff_html?: string;
  stats?: {
    additions: number;
    deletions: number;
    modifications: number;
  };
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
  async loginWithPassword(email: string, password: string, otpCode?: string): Promise<{ success: boolean; message: string; user?: User; token?: string }> {
    return fetchJson("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, otp_code: otpCode || null }),
    });
  },

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

  async getDiff(articleId: number, fromRev: number, toRev: number): Promise<DiffResult> {
    const res = await fetchJson<any>(`/api/v1/articles/${articleId}/revisions/diff/${fromRev}/${toRev}`);
    return {
      article_id: articleId,
      from_revision: res.old_revision_num ?? fromRev,
      to_revision: res.new_revision_num ?? toRev,
      diff_patch: res.diff_html || "",
      diff_html: res.diff_html,
      stats: res.stats,
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

  async applyCopilotEdit(params: {
    article_id: number;
    instruction: string;
  }): Promise<{ success: boolean; new_revision_num: number; content: string }> {
    return fetchJson(`/api/v1/articles/${params.article_id}/edit`, {
      method: "POST",
      body: JSON.stringify(params),
    });
  },

  // Telemetry
  async getTelemetry(): Promise<any> {
    return fetchJson("/api/v1/telemetry/latest");
  },

  async getTelemetryStats(): Promise<any> {
    return this.getTelemetry();
  },
};
