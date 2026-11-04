import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AgentDebugEntry, AgentRunStatus } from "../lib/useAgentRunStream";

type ChatDebugPanelProps = {
  debug: AgentDebugEntry[];
  lastEventAt: number | null;
  status: AgentRunStatus;
  running: boolean;
  runId?: string | null | undefined;
  model?: string | undefined;
  provider?: string | undefined;
};

const SILENCE_WARN_MS = 20_000;
const COPIED_FEEDBACK_MS = 1500;

const formatDelta = (ms: number): string => {
  if (ms < 1000) return `+${ms.toString()}ms`;
  const s = ms / 1000;
  return s < 10 ? `+${s.toFixed(1)}s` : `+${Math.round(s).toString()}s`;
};

const TYPE_COLOR: Record<string, string> = {
  error: "var(--c-err)",
  done: "var(--c-ok)",
  tool_call: "var(--accent)",
  tool_result: "var(--c-info, var(--accent))",
  approval_required: "var(--c-warn)",
};

export const ChatDebugPanel = ({
  debug,
  lastEventAt,
  status,
  running,
  runId,
  model,
  provider,
}: ChatDebugPanelProps) => {
  const { t } = useTranslation("agentChat");
  const endRef = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);

  // Tick once a second while running so the "silent for Ns" counter advances
  // even when no events arrive — that gap is exactly the hang we want to see.
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(id);
    };
  }, [running]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [debug.length]);

  const silenceMs = running && lastEventAt !== null ? now - lastEventAt : 0;
  const silent = silenceMs >= SILENCE_WARN_MS;

  const buildDebugText = (): string => {
    const header = [
      `agent debug — status: ${status}, events: ${debug.length.toString()}`,
      runId ? `run: ${runId}` : null,
      provider ? `provider: ${provider}` : null,
      model ? `model: ${model}` : null,
    ]
      .filter((line): line is string => line !== null)
      .join("\n");
    const lines = debug.map((entry, i) => {
      const prev = i > 0 ? debug[i - 1] : undefined;
      const delta = prev ? entry.at - prev.at : 0;
      const stamp = i === 0 ? "0" : formatDelta(delta);
      const count =
        (entry.count ?? 1) > 1 ? ` ×${(entry.count ?? 0).toString()}` : "";
      return `${stamp}\t${entry.type}${count}\t${entry.summary}`.trimEnd();
    });
    const tail =
      running && lastEventAt !== null
        ? `\n${t("debugPanel.silentText", { seconds: Math.floor(silenceMs / 1000) })}`
        : "";
    return `${header}\n\n${lines.join("\n")}${tail}`;
  };

  const handleCopy = (): void => {
    void navigator.clipboard
      .writeText(buildDebugText())
      .then(() => {
        setCopied(true);
        window.setTimeout(() => {
          setCopied(false);
        }, COPIED_FEEDBACK_MS);
      })
      .catch(() => {
        // Clipboard may be unavailable; nothing actionable to do here.
      });
  };

  return (
    <div
      style={{
        flexShrink: 0,
        maxHeight: "12.5rem",
        display: "flex",
        flexDirection: "column",
        borderTop: "1px solid var(--border)",
        background: "var(--bg-0)",
      }}
    >
      <div
        className="flex items-center justify-between"
        style={{ padding: "0.25rem 0.625rem" }}
      >
        <span
          className="dim"
          style={{ fontSize: "0.625rem", textTransform: "uppercase" }}
        >
          {t("debugPanel.title")}
        </span>
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          <span className="dim mono" style={{ fontSize: "0.625rem" }}>
            {status} · {debug.length}
          </span>
          <button
            type="button"
            className="btn xs ghost"
            title={t("debugPanel.copyTitle")}
            disabled={debug.length === 0}
            onClick={handleCopy}
          >
            {copied ? <Check size="0.6875rem" /> : <Copy size="0.6875rem" />}
            {copied ? t("debugPanel.copied") : t("debugPanel.copy")}
          </button>
        </div>
      </div>
      <div
        className="mono"
        style={{
          overflowY: "auto",
          padding: "0 0.625rem 0.375rem",
          fontSize: "0.65625rem",
        }}
      >
        {debug.length === 0 && (
          <div className="dim" style={{ padding: "0.25rem 0" }}>
            {t("debugPanel.noEvents")}
          </div>
        )}
        {debug.map((entry, i) => {
          const prev = i > 0 ? debug[i - 1] : undefined;
          const delta = prev ? entry.at - prev.at : 0;
          const isGap = delta >= 5000;
          return (
            <div
              key={i}
              className="flex"
              style={{ gap: "0.5rem", lineHeight: 1.6, alignItems: "baseline" }}
            >
              <span
                style={{
                  color: isGap ? "var(--c-warn)" : "var(--fg-3)",
                  minWidth: "3.25rem",
                  textAlign: "right",
                  flexShrink: 0,
                }}
              >
                {i === 0 ? "0" : formatDelta(delta)}
              </span>
              <span
                style={{
                  color: TYPE_COLOR[entry.type] ?? "var(--fg-1)",
                  minWidth: "6rem",
                  flexShrink: 0,
                }}
              >
                {entry.type}
                {(entry.count ?? 1) > 1
                  ? ` ×${(entry.count ?? 0).toString()}`
                  : ""}
              </span>
              <span
                className="truncate"
                style={{ color: "var(--fg-2)", minWidth: 0 }}
                title={entry.summary}
              >
                {entry.summary}
              </span>
            </div>
          );
        })}
        {running && (
          <div
            style={{
              color: silent ? "var(--c-err)" : "var(--fg-3)",
              paddingTop: "0.125rem",
            }}
          >
            ⏱{" "}
            {t("debugPanel.silentFor", {
              seconds: Math.floor(silenceMs / 1000),
            })}
            {silent ? t("debugPanel.silentStalled") : ""}
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
};
