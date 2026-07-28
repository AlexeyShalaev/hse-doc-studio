import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Copy, FileEdit, RefreshCw, Settings } from "lucide-react";
import { z } from "zod";
import { apiClient, ApiError, parseResp } from "@shared/api";
import { env } from "@shared/config";
import { toast } from "@shared/lib";

// ---------------------------------------------------------------------------
// ONLYOFFICE DocsAPI global (loaded at runtime from the Document Server
// container via a <script> tag — no npm package involved).
// ---------------------------------------------------------------------------

type DocEditorInstance = {
  destroyEditor?: () => void;
};

declare global {
  // Global augmentation must use `interface` (merges with the lib Window
  // type); a `type` alias cannot.
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  interface Window {
    DocsAPI?: {
      DocEditor: new (
        elementId: string,
        config: Record<string, unknown>,
      ) => DocEditorInstance;
    };
  }
}

// Module-level dedupe: api.js must be injected exactly once per app lifetime
// even if the pane unmounts/remounts (tab flips) or several panes race.
let docsApiLoader: Promise<void> | null = null;

const loadDocsApi = (src: string): Promise<void> => {
  if (window.DocsAPI) return Promise.resolve();
  docsApiLoader ??= new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => {
      resolve();
    };
    script.onerror = () => {
      // Allow a later retry to inject a fresh tag (the container may have
      // restarted on a different port).
      docsApiLoader = null;
      script.remove();
      reject(new Error(`Failed to load ${src}`));
    };
    document.head.appendChild(script);
  });
  return docsApiLoader;
};

// ---------------------------------------------------------------------------
// API contract (see backend office-editor endpoints).
// ---------------------------------------------------------------------------

const OfficeEditorResponseSchema = z.discriminatedUnion("state", [
  z.object({
    state: z.literal("ready"),
    editor_base_url: z.string(),
    api_js_url: z.string(),
    // Full DocsAPI.DocEditor config (document/editorConfig/token/…) — passed
    // through as-is; the frontend only forces width/height.
    config: z.record(z.string(), z.unknown()),
  }),
  z.object({ state: z.literal("image_missing"), image: z.string() }),
  z.object({ state: z.literal("unavailable"), detail: z.string() }),
]);

type OfficeEditorResponse = z.infer<typeof OfficeEditorResponseSchema>;
type ReadyResponse = Extract<OfficeEditorResponse, { state: "ready" }>;

type PaneState =
  | { kind: "loading" }
  | { kind: "image_missing"; image: string }
  | { kind: "unavailable"; detail: string }
  | { kind: "script_error" }
  | { kind: "ready"; editor: ReadyResponse };

// Keepalive period for the touch endpoint — half of the backend idle-reaper
// horizon, so an open editor tab keeps the container alive.
const TOUCH_INTERVAL_MS = 120_000;

// Cold start blocks the GET while the container boots — up to ~3 minutes. The
// shared client's default 30s timeout would kill it, so it's overridden.
const COLD_START_TIMEOUT_MS = 300_000;

export type OfficeEditorPaneProps = {
  projectId: string;
  docId: string;
};

export const OfficeEditorPane = ({
  projectId,
  docId,
}: OfficeEditorPaneProps) => {
  const { t } = useTranslation("documents");
  const navigate = useNavigate();
  const [state, setState] = useState<PaneState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<DocEditorInstance | null>(null);

  // 1) Ask the backend for the editor session config (boots the ONLYOFFICE
  //    container on demand — hence the long timeout + the spinner state).
  //    The initial state is already "loading"; retries reset it in `refetch`
  //    (an event handler), and the parent keys this pane by doc, so
  //    projectId/docId never change within a mounted instance.
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get(`/projects/${projectId}/documents/${docId}/office-editor`, {
        timeout: COLD_START_TIMEOUT_MS,
      })
      .then(parseResp(OfficeEditorResponseSchema))
      .then((resp) => {
        if (cancelled) return;
        if (resp.state === "ready") {
          setState({ kind: "ready", editor: resp });
        } else if (resp.state === "image_missing") {
          setState({ kind: "image_missing", image: resp.image });
        } else {
          setState({ kind: "unavailable", detail: resp.detail });
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const detail =
          e instanceof ApiError
            ? e.detail
            : e instanceof Error
              ? e.message
              : String(e);
        setState({ kind: "unavailable", detail });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, docId, attempt]);

  // 2) Once ready: load api.js from the container and instantiate the editor
  //    into an imperatively-created child div. DocsAPI replaces that div with
  //    its own iframe, so React must never own it — only the host wrapper.
  useEffect(() => {
    if (state.kind !== "ready") return;
    const host = hostRef.current;
    if (!host) return;
    const { api_js_url, config } = state.editor;
    const targetId = `office-editor-${docId}`;
    const target = document.createElement("div");
    target.id = targetId;
    target.style.width = "100%";
    target.style.height = "100%";
    host.replaceChildren(target);
    let cancelled = false;
    loadDocsApi(api_js_url)
      .then(() => {
        if (cancelled || !window.DocsAPI) return;
        editorRef.current = new window.DocsAPI.DocEditor(targetId, {
          ...config,
          width: "100%",
          height: "100%",
        });
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "script_error" });
      });
    return () => {
      cancelled = true;
      try {
        editorRef.current?.destroyEditor?.();
      } catch {
        // destroyEditor may throw if the iframe is already gone — ignore.
      }
      editorRef.current = null;
      host.replaceChildren();
    };
  }, [state, docId]);

  // 3) Keepalive: ping the touch endpoint while the editor is open so the
  //    backend idle-reaper doesn't stop the container under a live session.
  useEffect(() => {
    if (state.kind !== "ready") return;
    // Raw fetch on purpose: the shared client toasts every failed POST, and a
    // missed keepalive is background noise, not a user-actionable error.
    const touchUrl = `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/documents/${docId}/office-editor/touch`;
    const interval = window.setInterval(() => {
      void fetch(touchUrl, { method: "POST" }).catch(() => undefined);
    }, TOUCH_INTERVAL_MS);
    return () => {
      window.clearInterval(interval);
    };
  }, [state.kind, projectId, docId]);

  const refetch = () => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  };

  if (state.kind === "loading") {
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{ flex: 1, padding: 40, gap: 14, minHeight: 0 }}
      >
        <RefreshCw
          size={26}
          className="spin"
          style={{ color: "var(--accent)" }}
        />
        <div className="flex flex-col items-center" style={{ gap: 4 }}>
          <span style={{ fontSize: 13.5, fontWeight: 600 }}>
            {t("office.starting")}
          </span>
          <span className="dim" style={{ fontSize: 12 }}>
            {t("office.startingHint")}
          </span>
        </div>
      </div>
    );
  }

  if (state.kind === "image_missing") {
    const pullCommand = `docker pull ${state.image}`;
    const handleCopyCommand = () => {
      navigator.clipboard
        .writeText(pullCommand)
        .then(() => {
          toast.info(t("office.commandCopied"));
        })
        .catch(() => {
          toast.error(t("office.copyFailed"));
        });
    };
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{
          flex: 1,
          padding: 40,
          gap: 16,
          minHeight: 0,
          overflowY: "auto",
        }}
      >
        <div
          className="stripes flex items-center justify-center"
          style={{
            width: 240,
            height: 135,
            borderRadius: 6,
            border: "1px solid var(--border-strong)",
            color: "var(--fg-3)",
          }}
        >
          <FileEdit size={28} />
        </div>
        <span style={{ fontSize: 14, fontWeight: 600 }}>
          {t("office.notInstalledTitle")}
        </span>
        <p
          className="dim"
          style={{
            margin: 0,
            textAlign: "center",
            maxWidth: 440,
            fontSize: 12.5,
          }}
        >
          {t("office.notInstalledBody")}
        </p>
        <button
          type="button"
          className="btn primary"
          onClick={() => {
            void navigate("/settings/presentations");
          }}
        >
          <Settings size={12} />
          {t("office.installInSettings")}
        </button>
        <div className="flex flex-col items-center" style={{ gap: 6 }}>
          <span className="dim" style={{ fontSize: 11 }}>
            {t("office.pullHintSecondary")}
          </span>
          <div
            className="mono dim flex items-center"
            style={{
              gap: 8,
              padding: "4px 4px 4px 10px",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--bg-1)",
              fontSize: 10.5,
            }}
          >
            <span>{pullCommand}</span>
            <button
              type="button"
              className="btn xs tt"
              data-tt={t("office.copyCommand")}
              onClick={handleCopyCommand}
              style={{ width: 24, padding: 0 }}
            >
              <Copy size={10} />
            </button>
          </div>
        </div>
        <button type="button" className="btn" onClick={refetch}>
          <RefreshCw size={12} />
          {t("office.checkAgain")}
        </button>
      </div>
    );
  }

  if (state.kind === "unavailable" || state.kind === "script_error") {
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{
          flex: 1,
          padding: 40,
          gap: 16,
          minHeight: 0,
          overflowY: "auto",
        }}
      >
        <div
          className="stripes flex items-center justify-center"
          style={{
            width: 240,
            height: 135,
            borderRadius: 6,
            border: "1px solid var(--border-strong)",
            color: "var(--fg-3)",
          }}
        >
          <FileEdit size={28} />
        </div>
        <span style={{ fontSize: 14, fontWeight: 600 }}>
          {t("office.unavailableTitle")}
        </span>
        <p
          className="dim"
          style={{
            margin: 0,
            textAlign: "center",
            maxWidth: 440,
            fontSize: 12.5,
          }}
        >
          {state.kind === "script_error"
            ? t("office.scriptError")
            : state.detail}
        </p>
        <button type="button" className="btn" onClick={refetch}>
          <RefreshCw size={12} />
          {t("office.retry")}
        </button>
      </div>
    );
  }

  // ready — a slim status bar + the editor host. The iframe DocsAPI injects
  // fills the host (flex:1). After a save lands (DS callback) the backend
  // reconverts the PDF preview in the background, so «Превью» catches up
  // within seconds — no rebuild needed.
  return (
    <div
      className="flex flex-col"
      style={{ flex: 1, minHeight: 0, minWidth: 0 }}
    >
      <div
        className="flex items-center gap-2"
        style={{
          padding: "5px 10px",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        <FileEdit size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
        <span className="dim" style={{ fontSize: 11 }}>
          {t("office.autosaveNote")}
        </span>
      </div>
      <div ref={hostRef} style={{ flex: 1, minHeight: 0, minWidth: 0 }} />
    </div>
  );
};
