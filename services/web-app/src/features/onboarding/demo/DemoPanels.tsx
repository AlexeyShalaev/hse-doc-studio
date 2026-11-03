import { useTranslation } from "react-i18next";
import {
  Bot,
  Check,
  File,
  Folder,
  GitBranch,
  MessageSquare,
  Play,
  User,
} from "lucide-react";
import { clsx } from "clsx";
import type { DemoContent } from "./content";
import type { DemoState, DemoWorld, PreviewPage } from "./world";

const panel = {
  background: "var(--bg-1)",
  border: "1px solid var(--border)",
  borderRadius: "var(--r-3)",
  display: "flex",
  flexDirection: "column",
  minHeight: 0,
  overflow: "hidden",
} as const;

const head = {
  padding: "8px 12px",
  borderBottom: "1px solid var(--border)",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "var(--fg-2)",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
} as const;

export const CreatePanel = ({
  templateLabel,
  onCreate,
}: {
  templateLabel: string;
  onCreate: () => void;
}) => {
  const { t } = useTranslation("onboarding");
  return (
    <div style={{ ...panel, padding: 14, gap: 10 }} data-tour="demo-create">
      <span className="mono dim" style={{ fontSize: 10.5 }}>
        {t("demo.templateTitle")}
      </span>
      <div className="card" style={{ padding: 12 }}>
        <strong style={{ fontSize: 13.5 }}>{templateLabel}</strong>
        <div className="dim" style={{ fontSize: 11.5, marginTop: 4 }}>
          {t("demo.templateHint")}
        </div>
      </div>
      <button
        type="button"
        className="btn primary"
        onClick={onCreate}
        data-testid="demo-create-project"
      >
        {t("demo.createProject")}
      </button>
    </div>
  );
};

export const FilesPanel = ({
  state,
  world,
}: {
  state: DemoState;
  world: DemoWorld;
}) => {
  const { t } = useTranslation("onboarding");
  return (
    <div style={panel} data-tour="demo-files">
      <div style={head}>{t("demo.files")}</div>
      <ul style={{ listStyle: "none", margin: 0, padding: 6 }}>
        {state.files.map((file) => {
          const isDir = file.path.endsWith("/");
          return (
            <li key={file.path}>
              <button
                type="button"
                className={clsx(
                  "row-btn",
                  state.activePath === file.path && "active",
                )}
                disabled={isDir}
                style={{ width: "100%", justifyContent: "flex-start", gap: 8 }}
                onClick={() => {
                  world.openFile(file.path);
                }}
              >
                {isDir ? <Folder size={13} /> : <File size={13} />}
                <span className="mono" style={{ fontSize: 12 }}>
                  {file.path}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export const EditorPanel = ({
  state,
  world,
}: {
  state: DemoState;
  world: DemoWorld;
}) => {
  const { t } = useTranslation("onboarding");
  const file = state.files.find((f) => f.path === state.activePath);
  return (
    <div style={panel} data-tour="demo-editor">
      <div style={head}>
        <span>{t("demo.editor")}</span>
        <span className="mono" style={{ textTransform: "none" }}>
          {file?.path}
        </span>
      </div>
      {file ? (
        <textarea
          aria-label={t("demo.editorLabel", { path: file.path })}
          data-testid="demo-editor"
          spellCheck={false}
          value={file.content}
          onChange={(e) => {
            world.editFile(file.path, e.target.value);
          }}
          className="mono"
          style={{
            flex: 1,
            minHeight: 260,
            resize: "none",
            border: 0,
            outline: "none",
            padding: 12,
            fontSize: 12.5,
            lineHeight: 1.55,
            background: "var(--bg-0)",
            color: "var(--fg-0)",
          }}
        />
      ) : (
        <div className="dim" style={{ padding: 16, fontSize: 12.5 }}>
          {t("demo.createFirst")}
        </div>
      )}
    </div>
  );
};

const paper = {
  background: "#fff",
  color: "#111",
  width: "100%",
  aspectRatio: "210 / 297",
  boxShadow: "0 1px 4px rgba(0,0,0,.25)",
  padding: "9% 8%",
  fontFamily: "'Times New Roman', Times, serif",
  fontSize: 10,
  lineHeight: 1.45,
  display: "flex",
  flexDirection: "column",
} as const;

const Page = ({ page, n }: { page: PreviewPage; n: number }) => {
  const { t } = useTranslation("onboarding");
  if (page.kind === "title") {
    return (
      <div style={paper} aria-label={t("demo.page", { n })}>
        <div style={{ flex: 1 }} />
        <div
          data-testid="demo-preview-title"
          style={{ textAlign: "center", fontSize: 14, fontWeight: 700 }}
        >
          {page.title}
        </div>
        <div style={{ textAlign: "right", marginTop: 24 }}>{page.author}</div>
        <div style={{ flex: 1 }} />
        <div style={{ textAlign: "center" }}>{page.footer}</div>
      </div>
    );
  }
  return (
    <div style={paper} aria-label={t("demo.page", { n })}>
      {page.abstract && (
        <>
          <div style={{ textAlign: "center", fontWeight: 700 }}>
            {t("demo.abstract")}
          </div>
          <p style={{ textIndent: "1.25em", margin: "6px 0 12px" }}>
            {page.abstract}
          </p>
        </>
      )}
      {page.sections.map((section, i) => (
        <div key={section.heading}>
          <div style={{ fontWeight: 700, marginTop: 8 }}>
            {i + 1}. {section.heading}
          </div>
          <p style={{ textIndent: "1.25em", margin: "4px 0" }}>
            {section.text}
          </p>
        </div>
      ))}
      <div style={{ flex: 1 }} />
      <div style={{ textAlign: "center" }}>{n}</div>
    </div>
  );
};

export const PreviewPanel = ({
  state,
  world,
}: {
  state: DemoState;
  world: DemoWorld;
}) => {
  const { t } = useTranslation("onboarding");
  const running = state.build.status === "running";
  return (
    <div style={panel} data-tour="demo-preview">
      <div style={head}>
        <span>{t("demo.preview")}</span>
        <button
          type="button"
          className="btn primary sm"
          disabled={running || !state.project}
          data-tour="demo-build"
          data-testid="demo-build"
          onClick={() => {
            void world.build();
          }}
          style={{ textTransform: "none", letterSpacing: 0 }}
        >
          <Play size={12} />
          {running
            ? t("demo.building")
            : state.build.status === "done"
              ? t("demo.rebuild")
              : t("demo.build")}
        </button>
      </div>
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: 12,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          background: "var(--bg-2)",
          minHeight: 260,
        }}
      >
        {state.build.status === "done" && state.dirty && (
          <span className="chip" style={{ alignSelf: "flex-start" }}>
            {t("demo.previewStale")}
          </span>
        )}
        {running && (
          <pre
            className="mono"
            aria-live="polite"
            style={{ margin: 0, fontSize: 11.5, color: "var(--fg-1)" }}
          >
            {state.build.log.join("\n")}
          </pre>
        )}
        {!running && state.build.pages.length === 0 && (
          <span className="dim" style={{ fontSize: 12.5 }}>
            {t("demo.previewEmpty")}
          </span>
        )}
        {!running &&
          state.build.pages.map((page, i) => (
            <Page key={page.kind} page={page} n={i + 1} />
          ))}
      </div>
    </div>
  );
};

export type SideTab = "agent" | "review" | "git";

export const SidePanel = ({
  tab,
  onTab,
  state,
  world,
  content,
}: {
  tab: SideTab;
  onTab: (tab: SideTab) => void;
  state: DemoState;
  world: DemoWorld;
  content: DemoContent;
}) => {
  const { t } = useTranslation("onboarding");
  const open = state.comments.filter((c) => !c.resolved).length;
  const tabs: { id: SideTab; label: string; icon: typeof Bot }[] = [
    { id: "agent", label: t("demo.agent"), icon: Bot },
    {
      id: "review",
      label: `${t("demo.review")} (${String(open)})`,
      icon: MessageSquare,
    },
    { id: "git", label: t("demo.git"), icon: GitBranch },
  ];
  return (
    <div style={panel}>
      <div role="tablist" className="seg" style={{ margin: 8 }}>
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={clsx(tab === item.id && "active")}
            data-testid={`demo-tab-${item.id}`}
            onClick={() => {
              onTab(item.id);
            }}
          >
            <item.icon size={12} />
            {item.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        style={{ flex: 1, overflowY: "auto", padding: "0 12px 12px" }}
      >
        {tab === "agent" && (
          <div
            data-tour="demo-agent"
            className="flex flex-col"
            style={{ gap: 8 }}
          >
            {state.chat.length === 0 && (
              <span className="dim" style={{ fontSize: 12.5 }}>
                {t("demo.agentEmpty")}
              </span>
            )}
            <div
              aria-live="polite"
              className="flex flex-col"
              style={{ gap: 8 }}
            >
              {state.chat.map((m) => (
                <div
                  key={m.id}
                  className="card"
                  data-testid={`demo-chat-${m.role}`}
                  style={{
                    padding: 10,
                    fontSize: 12.5,
                    lineHeight: 1.5,
                    background: m.role === "user" ? "var(--bg-2)" : undefined,
                  }}
                >
                  <div
                    className="mono dim"
                    style={{ fontSize: 10.5, marginBottom: 4 }}
                  >
                    {m.role === "user" ? t("demo.you") : t("demo.agentName")}
                    {m.streaming ? ` · ${t("demo.agentTyping")}` : ""}
                  </div>
                  {m.text}
                </div>
              ))}
            </div>
            <div className="flex flex-col" style={{ gap: 6 }}>
              {content.prompts.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="btn sm"
                  disabled={state.agentBusy || !state.project}
                  data-testid={`demo-prompt-${p.id}`}
                  style={{ justifyContent: "flex-start", textAlign: "left" }}
                  onClick={() => {
                    void world.askAgent(p.id);
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        )}
        {tab === "review" && (
          <ul
            data-tour="demo-review"
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {state.comments.length === 0 && (
              <li className="dim" style={{ fontSize: 12.5 }}>
                {t("demo.reviewEmpty")}
              </li>
            )}
            {state.comments.map((c) => (
              <li
                key={c.id}
                className="card"
                data-testid={`demo-comment-${c.id}`}
                style={{
                  padding: 10,
                  fontSize: 12.5,
                  opacity: c.resolved ? 0.6 : 1,
                }}
              >
                <div
                  className="flex items-center"
                  style={{ gap: 6, marginBottom: 4 }}
                >
                  {c.kind === "agent" ? <Bot size={12} /> : <User size={12} />}
                  <strong style={{ fontSize: 12 }}>{c.author}</strong>
                </div>
                <div
                  className="mono dim"
                  style={{ fontSize: 11, marginBottom: 4 }}
                >
                  «{c.quote}»
                </div>
                <div>{c.text}</div>
                <div className="flex justify-end" style={{ marginTop: 6 }}>
                  {c.resolved ? (
                    <span className="chip">
                      <Check size={10} /> {t("demo.resolved")}
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="btn sm"
                      data-testid={`demo-resolve-${c.id}`}
                      onClick={() => {
                        world.resolveComment(c.id);
                      }}
                    >
                      {t("demo.resolve")}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {tab === "git" && (
          <div
            data-tour="demo-git"
            className="flex flex-col"
            style={{ gap: 10, fontSize: 12.5 }}
          >
            <div className="flex flex-col" style={{ gap: 4 }}>
              <span className="mono dim" style={{ fontSize: 10.5 }}>
                {t("demo.remote")}
              </span>
              <span className="mono" style={{ wordBreak: "break-all" }}>
                {state.git.remote ?? content.remoteUrl}
              </span>
            </div>
            {state.git.uncommitted && (
              <span className="chip" style={{ alignSelf: "flex-start" }}>
                {t("demo.uncommitted")}
              </span>
            )}
            <button
              type="button"
              className="btn primary sm"
              disabled={state.git.busy || !state.project}
              data-testid="demo-git-sync"
              onClick={() => {
                void world.sync();
              }}
            >
              <GitBranch size={12} />
              {state.git.busy
                ? t("demo.syncing")
                : state.git.remote
                  ? t("demo.sync")
                  : `${t("demo.connect")} · ${t("demo.sync")}`}
            </button>
            <span className="mono dim" style={{ fontSize: 10.5 }}>
              {t("demo.commits")}
            </span>
            {state.git.commits.length === 0 ? (
              <span className="dim">{t("demo.noCommits")}</span>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {state.git.commits.map((c) => (
                  <li
                    key={c.sha}
                    data-testid="demo-commit"
                    className="flex items-center"
                    style={{ gap: 8, padding: "4px 0" }}
                  >
                    <span className="mono" style={{ color: "var(--accent)" }}>
                      {c.sha}
                    </span>
                    <span className="flex-1 truncate">{c.message}</span>
                    <span className="dim" style={{ fontSize: 11 }}>
                      {c.pushed ? t("demo.pushed") : t("demo.notPushed")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
