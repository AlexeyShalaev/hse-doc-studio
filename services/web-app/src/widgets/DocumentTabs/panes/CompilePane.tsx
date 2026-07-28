import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  Download,
  HelpCircle,
  Play,
  RefreshCw,
  Sparkles,
  Square,
  Terminal,
} from "lucide-react";
import type { z } from "zod";
import { documentApi, getDocMeta } from "@entities/document";
import { useCancelDocCompile, useStartCompile } from "@entities/compile";
import type { DocumentResponseSchema } from "@entities/document";
import { apiClient } from "@shared/api";
import { env } from "@shared/config";
import { useWorkspaceStore } from "@shared/lib";

type Document = z.infer<typeof DocumentResponseSchema>;

export type CompilePaneProps = {
  projectId: string;
  doc: Document;
};

type LocalStatus = "idle" | "running" | "success" | "failure" | "cancelled";

const ERROR_RE =
  /^!|^l\.\d|Error:|Fatal error|Emergency stop|Undefined control/;
const WARN_RE = /Warning|Overfull|Underfull|Missing character/;

// Colour a latexmk log line by severity so errors/warnings stand out from the
// reams of normal output — purely visual, no parsing of structure.
const logLineColor = (line: string): string => {
  if (ERROR_RE.test(line)) return "var(--c-err)";
  if (WARN_RE.test(line)) return "var(--c-warn)";
  return "var(--fg-1)";
};

const logFileUrl = (projectId: string, logPath: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${logPath}`;

// latexmk writes logs to `<src_dir>/.build/<doc_id>/<stem>.log` next to the
// source — see DockerCompileExecutor. Mirror that layout here so the
// "last build log" view and "Скачать .log" point at the right file.
const buildLogPath = (texPath: string, docId: string): string => {
  const norm = texPath.replace(/\\/g, "/");
  const lastSlash = norm.lastIndexOf("/");
  const parent = lastSlash >= 0 ? norm.slice(0, lastSlash) : "";
  const basename = lastSlash >= 0 ? norm.slice(lastSlash + 1) : norm;
  const stem = basename.replace(/\.tex$/i, "");
  return parent
    ? `${parent}/.build/${docId}/${stem}.log`
    : `.build/${docId}/${stem}.log`;
};

export const CompilePane = ({ projectId, doc }: CompilePaneProps) => {
  const { t } = useTranslation("documents");
  // Pass the doc so meta.file (→ .build log path) comes from the API.
  const meta = getDocMeta(doc.id, doc);
  const {
    start: handleRebuild,
    isRunning: isStarting,
    slot,
  } = useStartCompile(projectId, doc.id);
  const { cancel: handleCancel, isCancelling } = useCancelDocCompile(
    projectId,
    doc.id,
  );
  // Live stream state lives in the global store, so it survives unmounts
  // when the user switches tabs/routes during a build.

  // Fallback view when no live stream owns the pane: on-disk .log + status
  // from the persisted compile record.
  const [diskLines, setDiskLines] = useState<string[]>([]);
  const [recordStatus, setRecordStatus] = useState<LocalStatus>("idle");
  const logRef = useRef<HTMLDivElement>(null);

  const liveOwnsPane = slot !== undefined;
  const logLines = liveOwnsPane ? slot.logLines : diskLines;
  const status: LocalStatus = liveOwnsPane ? slot.status : recordStatus;
  const doneInfo = liveOwnsPane ? slot.doneInfo : null;

  // Auto-scroll to bottom on new lines.
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines.length]);

  // Load on-disk .log + persisted compile record when no live stream owns
  // the pane (between builds, or after a fresh app open).
  useEffect(() => {
    if (liveOwnsPane) return;
    let cancelled = false;

    const logPath = buildLogPath(meta.file, doc.id);
    void apiClient
      .get(`/projects/${projectId}/files/${logPath}`, { responseType: "text" })
      .then((r) => {
        if (cancelled) return;
        const log = String(r.data ?? "");
        if (log) setDiskLines(log.split(/\r?\n/));
      })
      .catch(() => {
        // No log on disk yet — keep the "запустите сборку" placeholder.
      });

    if (doc.last_compile_id) {
      const lastId = doc.last_compile_id;
      void documentApi
        .getCompile(projectId, doc.id, lastId)
        .then((detail) => {
          if (cancelled) return;
          const terminalStatuses: LocalStatus[] = [
            "success",
            "failure",
            "cancelled",
          ];
          setRecordStatus(
            terminalStatuses.includes(detail.status as LocalStatus)
              ? (detail.status as LocalStatus)
              : "idle",
          );
          setDiskLines((prev) => {
            if (prev.length > 0) return prev; // disk log won
            const log = detail.log ?? "";
            return log ? log.split(/\r?\n/) : prev;
          });
        })
        .catch(() => {
          // Ignore — disk lookup may still have populated diskLines.
        });
    }

    return () => {
      cancelled = true;
    };
  }, [liveOwnsPane, doc.last_compile_id, doc.id, projectId, meta.file]);

  const logPath = buildLogPath(meta.file, doc.id);
  const logHref = logFileUrl(projectId, logPath);

  const askAgent = useWorkspaceStore((state) => state.askAgent);
  const handleFixWithAi = () => {
    askAgent(
      t("compile.fixPrompt", {
        code: meta.code,
        docId: doc.id,
        logPath,
        file: meta.file,
      }),
    );
  };
  const handleExplain = () => {
    askAgent(
      t("compile.explainPrompt", {
        code: meta.code,
        docId: doc.id,
        logPath,
      }),
    );
  };

  const isRunning = status === "running" || isStarting;
  const isDone = status === "success";
  const isFailed = status === "failure";
  const isCancelled = status === "cancelled";
  const isStalled = liveOwnsPane && slot.isStalled;

  // Ask for notification permission once a build is actually running (a real
  // user gesture preceded it), so a long build can ping the OS when it ends.
  useEffect(() => {
    if (
      isRunning &&
      "Notification" in window &&
      Notification.permission === "default"
    ) {
      void Notification.requestPermission();
    }
  }, [isRunning]);

  // Fire a desktop notification when a build finishes while the window is in the
  // background — long builds (up to 240s) often run while the student is elsewhere.
  const prevStatusRef = useRef<LocalStatus>(status);
  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = status;
    if (prev !== "running") return;
    if (status !== "success" && status !== "failure") return;
    if (document.visibilityState !== "hidden") return;
    if (!("Notification" in window) || Notification.permission !== "granted") {
      return;
    }
    const body =
      status === "success"
        ? doneInfo?.pages != null
          ? t("compile.notification.successPages", {
              code: meta.code,
              count: doneInfo.pages,
            })
          : t("compile.notification.success", { code: meta.code })
        : t("compile.notification.failure", { code: meta.code });
    try {
      new Notification(t("compile.notification.title"), { body });
    } catch {
      // Notifications can be unavailable (permissions revoked, headless) — ignore.
    }
  }, [status, meta.code, doneInfo, t]);

  return (
    <div className="flex flex-col" style={{ flex: 1, minHeight: 0 }}>
      <div
        className="flex items-center justify-between"
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <div className="flex items-center gap-3">
          {/* engine === null → copy-only variant (pptx/reveal): the build just
              runs checks and publishes the file, no LaTeX engine involved. */}
          <strong style={{ fontSize: 12.5 }}>
            {doc.engine === null
              ? t("compile.noCompilation")
              : (doc.engine ?? "xelatex")}{" "}
            · {meta.file}
          </strong>
          {isRunning && (
            <div className="flex items-center gap-2">
              <span className="dot live" />
              <span
                className="mono"
                style={{ fontSize: 11, color: "var(--c-info)" }}
              >
                {t("compile.running")}
              </span>
            </div>
          )}
          {isDone && (
            <span className="sev ok">
              <span className="dot ok" />
              {t("compile.done")}
              {doneInfo?.pages != null && (
                <span className="dim" style={{ marginLeft: 6 }}>
                  {t("compile.donePages", { count: doneInfo.pages })}
                </span>
              )}
            </span>
          )}
          {isFailed && (
            <span className="sev err">
              <span className="dot err" />
              {t("compile.failed")}
            </span>
          )}
          {isCancelled && (
            <span className="sev">
              <span className="dot pending" />
              {t("compile.cancelled")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isRunning ? (
            <button
              type="button"
              className="btn xs"
              onClick={handleCancel}
              disabled={isCancelling}
              style={{
                color: isStalled ? "var(--c-err)" : undefined,
                borderColor: isStalled ? "var(--c-err)" : undefined,
              }}
            >
              {isStalled ? <AlertTriangle size={11} /> : <Square size={11} />}
              {t("compile.cancel")}
            </button>
          ) : (
            <button type="button" className="btn xs" onClick={handleRebuild}>
              <RefreshCw size={11} />
              {t("compile.rebuild")}
            </button>
          )}
          {isFailed && (
            <>
              <button
                type="button"
                className="btn xs ghost"
                onClick={handleExplain}
                title={t("compile.explainTitle")}
              >
                <HelpCircle size={11} />
                {t("compile.explain")}
              </button>
              <button
                type="button"
                className="btn xs"
                onClick={handleFixWithAi}
                title={t("compile.fixWithAiTitle")}
              >
                <Sparkles size={11} />
                {t("compile.fixWithAi")}
              </button>
            </>
          )}
          <a
            href={logHref}
            download={`${doc.id}.log`}
            className="btn xs ghost"
            title={t("compile.downloadLogTitle", { path: logPath })}
          >
            <Download size={11} />
            {t("compile.downloadLog")}
          </a>
        </div>
      </div>

      {isStalled && (
        <div
          className="flex items-start gap-2"
          style={{
            padding: "8px 16px",
            fontSize: 11.5,
            background: "var(--c-err-soft, rgba(239, 68, 68, 0.08))",
            borderBottom: "1px solid var(--c-err)",
            color: "var(--c-err)",
            lineHeight: 1.5,
          }}
        >
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>{t("compile.stalledWarning")}</span>
        </div>
      )}

      <div style={{ padding: "0 16px", background: "var(--bg-1)" }}>
        <div className="progress" style={{ height: 3 }}>
          <div
            style={{
              width: isRunning ? "60%" : isDone || isFailed ? "100%" : "0%",
              background: isFailed ? "var(--c-err)" : undefined,
            }}
          />
        </div>
      </div>

      <div
        ref={logRef}
        style={{
          flex: 1,
          overflow: "auto",
          padding: 16,
          background: "var(--bg-0)",
          fontFamily: "var(--font-mono)",
          fontSize: 11.5,
          lineHeight: 1.6,
        }}
      >
        {logLines.length === 0 && !isRunning && (
          <div
            className="flex flex-col items-center justify-center"
            style={{ height: "100%", color: "var(--fg-3)", gap: 12 }}
          >
            <Terminal size={32} />
            <span
              className="mono"
              style={{ fontSize: 10, textTransform: "uppercase" }}
            >
              {t("compile.runBuild")}
            </span>
            <button
              type="button"
              className="btn primary"
              onClick={handleRebuild}
              disabled={isRunning}
            >
              <Play size={11} />
              {t("compile.runXelatex")}
            </button>
          </div>
        )}
        {logLines.map((line, i) => (
          <div
            key={i}
            style={{ color: logLineColor(line), whiteSpace: "pre-wrap" }}
          >
            <span style={{ color: "var(--fg-3)", marginRight: 8 }}>
              {String(i + 1).padStart(3, " ")}
            </span>
            {line}
          </div>
        ))}
        {isRunning && (
          <div className="flex items-center gap-1" style={{ marginTop: 4 }}>
            <span style={{ color: "var(--c-ok)" }}>▮</span>
            <span
              className="blink"
              style={{ color: "var(--c-ok)", marginLeft: -2 }}
            >
              ▌
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
