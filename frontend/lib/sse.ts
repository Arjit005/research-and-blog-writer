/**
 * Resumable Server-Sent Events (SSE) connector.
 *
 * Handles Last-Event-ID tracking, automated exponential backoff reconnection,
 * and dispatching agent steps and completed events. After the retry budget is
 * exhausted the error callback fires so the caller can reconcile the real run
 * state through `GET /api/v1/runs/{run_id}` instead of dead-ending the UI.
 */

import { apiUrl } from "./api";

export type SSEPayload = Record<string, unknown>;

export interface SSEEvent {
  id?: string;
  type: string;
  data: SSEPayload;
}

export type EventCallback = (event: SSEEvent) => void;
export type ErrorCallback = (error: Error) => void;
export type CompleteCallback = (data: SSEPayload) => void;

const MAX_RECONNECT_ATTEMPTS = 5;

export class ResumableSSEClient {
  private runId: string;
  private lastEventId: string;
  private eventSource: EventSource | null = null;
  private onEventCb: EventCallback;
  private onErrorCb: ErrorCallback;
  private onCompleteCb: CompleteCallback;
  private isClosed = false;
  private retryAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    runId: string,
    onEvent: EventCallback,
    onError: ErrorCallback,
    onComplete: CompleteCallback,
    initialEventId: string = "0"
  ) {
    this.runId = runId;
    this.onEventCb = onEvent;
    this.onErrorCb = onError;
    this.onCompleteCb = onComplete;
    this.lastEventId = initialEventId;
  }

  public connect(): void {
    if (this.isClosed || this.eventSource) return;

    const url = apiUrl(
      `/api/v1/runs/${this.runId}/events?after_seq=${encodeURIComponent(this.lastEventId)}`
    );
    const es = new EventSource(url, { withCredentials: true });
    this.eventSource = es;

    const handleMessage = (type: string, ev: MessageEvent) => {
      if (ev.lastEventId) {
        this.lastEventId = ev.lastEventId;
      }
      try {
        const parsed: unknown = JSON.parse(String(ev.data));
        const data: SSEPayload = typeof parsed === "object" && parsed !== null ? (parsed as SSEPayload) : {};
        const eventObj: SSEEvent = {
          id: ev.lastEventId,
          type,
          data,
        };
        this.onEventCb(eventObj);

        if (type === "completed") {
          this.close();
          this.onCompleteCb(data);
        } else if (type === "error" || type === "cancelled") {
          this.close();
          this.onErrorCb(new Error(this.messageFromPayload(data, type)));
        }
      } catch (err) {
        console.error("Failed to parse SSE event payload:", err, ev.data);
      }
    };

    // Listen to standard named events
    const eventNames = ["run_start", "status", "step", "task_done", "completed", "error", "cancelled"];
    eventNames.forEach((name) => {
      es.addEventListener(name, (ev: Event) => handleMessage(name, ev as MessageEvent));
    });

    es.onopen = () => {
      this.retryAttempts = 0;
    };

    es.onerror = () => {
      if (this.isClosed) return;
      es.close();
      this.eventSource = null;

      // Exponential backoff reconnect up to 5 attempts
      if (this.retryAttempts < MAX_RECONNECT_ATTEMPTS) {
        const timeout = Math.min(1000 * Math.pow(2, this.retryAttempts), 10_000);
        this.retryAttempts++;
        this.reconnectTimer = setTimeout(() => {
          this.reconnectTimer = null;
          if (!this.isClosed) this.connect();
        }, timeout);
      } else {
        this.onErrorCb(
          new Error(
            `Live connection lost after ${MAX_RECONNECT_ATTEMPTS} reconnect attempts. Checking the run state on the server…`
          )
        );
      }
    };
  }

  private messageFromPayload(data: SSEPayload, type: string): string {
    const message = data.message;
    if (typeof message === "string" && message.trim()) return message;
    return type === "cancelled" ? "Research run was cancelled." : "Pipeline execution failed.";
  }

  public close(): void {
    this.isClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
