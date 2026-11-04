/**
 * Resumable Server-Sent Events (SSE) connector.
 * Handles Last-Event-ID tracking, automated exponential backoff reconnection,
 * and dispatching agent steps and completed events.
 */

export interface SSEEvent {
  id?: string;
  type: string;
  data: any;
}

export type EventCallback = (event: SSEEvent) => void;
export type ErrorCallback = (error: any) => void;
export type CompleteCallback = (data: any) => void;

export class ResumableSSEClient {
  private runId: string;
  private lastEventId: string = "0";
  private eventSource: EventSource | null = null;
  private onEventCb: EventCallback;
  private onErrorCb: ErrorCallback;
  private onCompleteCb: CompleteCallback;
  private isClosed: boolean = false;
  private retryAttempts: number = 0;

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
    if (this.isClosed) return;

    const url = `/api/v1/runs/${this.runId}/events?after_seq=${encodeURIComponent(this.lastEventId)}`;
    const es = new EventSource(url, { withCredentials: true });
    this.eventSource = es;

    const handleMessage = (type: string, ev: MessageEvent) => {
      if (ev.lastEventId) {
        this.lastEventId = ev.lastEventId;
      }
      try {
        const parsed = JSON.parse(ev.data);
        const eventObj: SSEEvent = {
          id: ev.lastEventId,
          type,
          data: parsed,
        };
        this.onEventCb(eventObj);

        if (type === "completed") {
          this.close();
          this.onCompleteCb(parsed);
        } else if (type === "error" || type === "cancelled") {
          this.close();
          this.onErrorCb(parsed);
        }
      } catch (err) {
        console.error("Failed to parse SSE event payload:", err, ev.data);
      }
    };

    // Listen to standard named events
    const eventNames = ["run_start", "status", "step", "task_done", "completed", "error", "cancelled"];
    eventNames.forEach((name) => {
      es.addEventListener(name, (ev: MessageEvent) => handleMessage(name, ev));
    });

    es.onopen = () => {
      this.retryAttempts = 0;
    };

    es.onerror = (e) => {
      if (this.isClosed) return;
      es.close();

      // Exponential backoff reconnect up to 5 attempts
      if (this.retryAttempts < 5) {
        const timeout = Math.min(1000 * Math.pow(2, this.retryAttempts), 10000);
        this.retryAttempts++;
        setTimeout(() => {
          if (!this.isClosed) this.connect();
        }, timeout);
      } else {
        this.onErrorCb(new Error("Connection lost after repeated reconnect attempts."));
      }
    };
  }

  public close(): void {
    this.isClosed = true;
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
