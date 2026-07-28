export type SSEEvent<T> = { type: string; data: T };

export function createSSEStream<T>(
  url: string,
  onEvent: (event: SSEEvent<T>) => void,
  onError?: (error: Event) => void,
): () => void {
  const source = new EventSource(url);

  const handleMessage = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data as string) as T;
      onEvent({ type: event.type || "message", data });
    } catch {
      // ignore malformed JSON
    }
  };

  // Listen to named events via onmessage for "message" type
  source.onmessage = handleMessage;

  // For SSE with named events (event: log / event: done), we need to
  // add listeners dynamically. Since EventSource doesn't expose all event types,
  // we rely on the caller knowing the event types or use a generic approach.
  // The SSE stream events (log, done) need explicit listeners:
  source.addEventListener("log", handleMessage);
  source.addEventListener("done", handleMessage);

  source.onerror = (event) => {
    onError?.(event);
  };

  return () => {
    source.close();
  };
}
