import { useCallback, useEffect, useRef, useState } from "react";

import { i18n } from "@shared/lib";

// The backend streams an agent turn as named SSE events. The shared
// createSSEStream only wires "log"/"done", so this hook attaches listeners for
// the full agent event taxonomy directly on an EventSource.

export type AgentRunStatus =
  | "idle"
  | "running"
  | "awaiting_approval"
  | "done"
  | "error";

export type PendingApproval = {
  callId: string;
  name: string;
  args: Record<string, unknown>;
  kind: string;
};

export type QuestionOption = {
  label: string;
  description?: string;
};

export type QuestionSpec = {
  header?: string;
  question: string;
  multiSelect?: boolean;
  options: QuestionOption[];
};

// One ask_user call awaiting answers (carries 1+ questions).
export type PendingQuestion = {
  callId: string;
  questions: QuestionSpec[];
};

// One row in the debug timeline. Consecutive token events are coalesced into a
// single growing entry so the log stays compact while still showing progress.
export type AgentDebugEntry = {
  at: number;
  type: string;
  summary: string;
  count?: number;
};

export type AgentStreamState = {
  status: AgentRunStatus;
  liveText: string;
  approvals: PendingApproval[];
  questions: PendingQuestion[];
  usage: { input: number; output: number; total: number } | null;
  doneStatus: string | null;
  error: string | null;
  // Diagnostics: raw event timeline + when the last event arrived (for the
  // "agent is silent for Ns" hang detector).
  debug: AgentDebugEntry[];
  lastEventAt: number | null;
};

const INITIAL_STATE: AgentStreamState = {
  status: "idle",
  liveText: "",
  approvals: [],
  questions: [],
  usage: null,
  doneStatus: null,
  error: null,
  debug: [],
  lastEventAt: null,
};

const MAX_DEBUG_ENTRIES = 300;

const AGENT_EVENTS = [
  "token",
  "message",
  "tool_call",
  "tool_result",
  "iteration",
  "usage",
  "compaction",
  "approval_required",
  "question_required",
  "done",
  "error",
] as const;

const asString = (value: unknown): string =>
  typeof value === "string" ? value : "";
const asNumber = (value: unknown): number =>
  typeof value === "number" ? value : 0;
const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};

const parseQuestions = (value: unknown): QuestionSpec[] => {
  if (!Array.isArray(value)) return [];
  const out: QuestionSpec[] = [];
  for (const raw of value) {
    const record = asRecord(raw);
    const question = asString(record.question);
    if (!question) continue;
    const options: QuestionOption[] = [];
    const optionsRaw = Array.isArray(record.options) ? record.options : [];
    for (const optionRaw of optionsRaw) {
      const optionRecord = asRecord(optionRaw);
      const label = asString(optionRecord.label);
      if (!label) continue;
      const description = asString(optionRecord.description);
      options.push(description ? { label, description } : { label });
    }
    const spec: QuestionSpec = { question, options };
    const header = asString(record.header);
    if (header) spec.header = header;
    if (record.multiSelect === true) spec.multiSelect = true;
    out.push(spec);
  }
  return out;
};

const summarizeEvent = (
  type: string,
  data: Record<string, unknown>,
): string => {
  switch (type) {
    case "token":
      return "";
    case "message":
      return asString(data.role) || i18n.t("agentChat:debugEvent.message");
    case "tool_call":
      return `${asString(data.name)} ${JSON.stringify(data.args ?? {})}`;
    case "tool_result":
      return `${asString(data.name)} ${data.is_error ? i18n.t("agentChat:debugEvent.toolError") : i18n.t("agentChat:debugEvent.toolOk")}`;
    case "iteration":
      return `#${asNumber(data.n).toString()}`;
    case "usage":
      return i18n.t("agentChat:debugEvent.tokens", {
        count: asNumber(data.total_tokens),
      });
    case "approval_required":
      return asString(data.name);
    case "question_required":
      return i18n.t("agentChat:debugEvent.questionToUser");
    case "compaction":
      return i18n.t("agentChat:debugEvent.contextCompaction");
    case "done":
      return asString(data.status) || i18n.t("agentChat:debugEvent.done");
    case "error":
      return asString(data.message) || i18n.t("agentChat:debugEvent.error");
    default:
      return "";
  }
};

const appendDebug = (
  prev: AgentDebugEntry[],
  type: string,
  data: Record<string, unknown>,
  at: number,
): AgentDebugEntry[] => {
  // Coalesce a burst of token deltas into one entry that just counts chunks.
  if (type === "token") {
    const last = prev[prev.length - 1];
    if (last?.type === "token") {
      return [
        ...prev.slice(0, -1),
        { ...last, at, count: (last.count ?? 1) + 1 },
      ];
    }
    const next = [...prev, { at, type, summary: "", count: 1 }];
    return next.length > MAX_DEBUG_ENTRIES
      ? next.slice(-MAX_DEBUG_ENTRIES)
      : next;
  }
  const next = [...prev, { at, type, summary: summarizeEvent(type, data) }];
  return next.length > MAX_DEBUG_ENTRIES
    ? next.slice(-MAX_DEBUG_ENTRIES)
    : next;
};

export type UseAgentRunStreamReturn = {
  state: AgentStreamState;
  start: (url: string) => void;
  reset: () => void;
};

type AgentStreamCallbacks = {
  // Fired when a full message lands so the caller can refetch the persisted transcript.
  onMessage?: () => void;
  // Fired on the terminal event with the run's final status.
  onDone?: (status: string) => void;
  // Fired when a tool finished, with the call's args (resolved from the paired
  // tool_call event). Lets the caller apply client-side effects of app-control
  // tools — e.g. set_theme, which the backend only persists server-side.
  onToolResult?: (
    name: string,
    args: Record<string, unknown>,
    isError: boolean,
  ) => void;
};

export const useAgentRunStream = (
  callbacks: AgentStreamCallbacks = {},
): UseAgentRunStreamReturn => {
  const [state, setState] = useState<AgentStreamState>(INITIAL_STATE);
  const sourceRef = useRef<EventSource | null>(null);
  const callbacksRef = useRef(callbacks);
  // tool_call carries the args, tool_result carries the outcome — pair them by
  // call_id so onToolResult gets both.
  const toolArgsRef = useRef(
    new Map<string, { name: string; args: Record<string, unknown> }>(),
  );

  useEffect(() => {
    callbacksRef.current = callbacks;
  });

  useEffect(() => {
    return () => {
      sourceRef.current?.close();
      sourceRef.current = null;
    };
  }, []);

  const start = useCallback((url: string) => {
    sourceRef.current?.close();
    toolArgsRef.current.clear();
    setState({ ...INITIAL_STATE, status: "running" });
    const source = new EventSource(url);
    sourceRef.current = source;

    const handle = (type: string) => (event: MessageEvent) => {
      let data: Record<string, unknown> = {};
      try {
        data = asRecord(JSON.parse(event.data as string));
      } catch {
        return;
      }
      const now = Date.now();
      setState((prev) => ({
        ...reduceEvent(prev, type, data),
        debug: appendDebug(prev.debug, type, data, now),
        lastEventAt: now,
      }));
      if (type === "message") {
        callbacksRef.current.onMessage?.();
      }
      if (type === "tool_call") {
        const callId = asString(data.call_id);
        if (callId)
          toolArgsRef.current.set(callId, {
            name: asString(data.name),
            args: asRecord(data.args),
          });
      }
      if (type === "tool_result") {
        const callId = asString(data.call_id);
        const tracked = callId ? toolArgsRef.current.get(callId) : undefined;
        if (callId) toolArgsRef.current.delete(callId);
        callbacksRef.current.onToolResult?.(
          asString(data.name) || (tracked?.name ?? ""),
          tracked?.args ?? {},
          data.is_error === true,
        );
      }
      if (type === "done" || type === "error") {
        callbacksRef.current.onDone?.(asString(data.status) || type);
        source.close();
        sourceRef.current = null;
      }
    };

    for (const name of AGENT_EVENTS) {
      source.addEventListener(name, handle(name));
    }
    source.onerror = () => {
      setState((prev) =>
        prev.status === "running"
          ? {
              ...prev,
              status: "error",
              error: i18n.t("agentChat:stream.connectionLost"),
            }
          : prev,
      );
    };
  }, []);

  const reset = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
    toolArgsRef.current.clear();
    setState(INITIAL_STATE);
  }, []);

  return { state, start, reset };
};

function reduceEvent(
  prev: AgentStreamState,
  type: string,
  data: Record<string, unknown>,
): AgentStreamState {
  switch (type) {
    case "token":
      return { ...prev, liveText: prev.liveText + asString(data.text) };
    case "message":
      // A full message landed; the caller refetches the transcript, so clear the live buffer.
      return { ...prev, liveText: "" };
    case "usage":
      return {
        ...prev,
        usage: {
          input: asNumber(data.input_tokens),
          output: asNumber(data.output_tokens),
          total: asNumber(data.total_tokens),
        },
      };
    case "approval_required":
      return {
        ...prev,
        status: "awaiting_approval",
        approvals: [
          ...prev.approvals,
          {
            callId: asString(data.call_id),
            name: asString(data.name),
            args: asRecord(data.args),
            kind: asString(data.kind),
          },
        ],
      };
    case "question_required":
      return {
        ...prev,
        status: "awaiting_approval",
        questions: [
          ...prev.questions,
          {
            callId: asString(data.call_id),
            questions: parseQuestions(data.questions),
          },
        ],
      };
    case "done": {
      const status = asString(data.status) || "done";
      // Упавший ран приходит терминальным `done` со status=failed и message —
      // без этой ветки агент «молчал»: ошибка жила только в логах бэкенда.
      const failed = status === "failed" || status === "interrupted";
      return {
        ...prev,
        status:
          status === "awaiting_approval"
            ? "awaiting_approval"
            : failed
              ? "error"
              : "done",
        doneStatus: status,
        error: failed
          ? asString(data.message) || i18n.t("agentChat:stream.error")
          : prev.error,
      };
    }
    case "error":
      return {
        ...prev,
        status: "error",
        error: asString(data.message) || i18n.t("agentChat:stream.error"),
      };
    default:
      return prev;
  }
}
