import { useEffect, useRef, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AgentTool } from "@entities/agent-chat";

type ChatToolsMenuProps = {
  tools: AgentTool[];
  // null = all tools enabled; otherwise the explicit enabled set.
  enabled: string[] | null;
  onChange: (enabled: string[] | null) => void;
  disabled?: boolean;
};

// i18n keys + grouping for the raw tool names from the backend. `group` is a
// stable group id resolved to a localized label via GROUP_LABEL_KEY at render.
const TOOL_META: Record<string, { labelKey: string; group: string }> = {
  read_tex: { labelKey: "tools.readTex", group: "docsText" },
  edit_tex: { labelKey: "tools.editTex", group: "docsText" },
  grep_project: { labelKey: "tools.grepProject", group: "docsText" },
  list_documents: { labelKey: "tools.listDocuments", group: "docsText" },
  compile_document: { labelKey: "tools.compileDocument", group: "buildChecks" },
  package_project: { labelKey: "tools.packageProject", group: "buildChecks" },
  list_check_findings: {
    labelKey: "tools.listCheckFindings",
    group: "buildChecks",
  },
  trace_requirements: {
    labelKey: "tools.traceRequirements",
    group: "buildChecks",
  },
  preview_requirements_format: {
    labelKey: "tools.previewRequirementsFormat",
    group: "buildChecks",
  },
  set_requirements_format: {
    labelKey: "tools.setRequirementsFormat",
    group: "buildChecks",
  },
  set_theme: { labelKey: "tools.setTheme", group: "settings" },
  set_engine: { labelKey: "tools.setEngine", group: "settings" },
  set_language: { labelKey: "tools.setLanguage", group: "settings" },
  set_project_meta: { labelKey: "tools.setProjectMeta", group: "settings" },
  read_pdf: { labelKey: "tools.readPdf", group: "docsText" },
  ask_user: { labelKey: "tools.askUser", group: "other" },
  vcs_status: { labelKey: "tools.vcsStatus", group: "versions" },
  vcs_list_history: { labelKey: "tools.vcsListHistory", group: "versions" },
  vcs_diff: { labelKey: "tools.vcsDiff", group: "versions" },
  vcs_save_snapshot: { labelKey: "tools.vcsSaveSnapshot", group: "versions" },
  vcs_restore: { labelKey: "tools.vcsRestore", group: "versions" },
  create_project: { labelKey: "tools.createProject", group: "projects" },
  list_projects: { labelKey: "tools.listProjects", group: "projects" },
  list_templates: { labelKey: "tools.listTemplates", group: "projects" },
};

const GROUP_ORDER = [
  "docsText",
  "buildChecks",
  "versions",
  "projects",
  "settings",
  "other",
];

const GROUP_LABEL_KEY: Record<string, string> = {
  docsText: "tools.groupDocsText",
  buildChecks: "tools.groupBuildChecks",
  versions: "tools.groupVersions",
  projects: "tools.groupProjects",
  settings: "tools.groupSettings",
  other: "tools.groupOther",
};

const metaFor = (name: string): { labelKey: string | null; group: string } =>
  TOOL_META[name] ?? { labelKey: null, group: "other" };

export const ChatToolsMenu = ({
  tools,
  enabled,
  onChange,
  disabled,
}: ChatToolsMenuProps) => {
  const { t } = useTranslation("agentChat");
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (rootRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [open]);

  const names = tools.map((t) => t.name);
  const isOn = (name: string): boolean =>
    enabled === null || enabled.includes(name);
  const enabledCount = names.filter(isOn).length;

  const emit = (nextOn: Set<string>): void => {
    // Collapse "everything on" back to null so new tools are on by default.
    onChange(nextOn.size >= names.length ? null : [...nextOn]);
  };

  const toggle = (name: string): void => {
    const set = new Set(
      enabled === null ? names : enabled.filter((n) => names.includes(n)),
    );
    if (set.has(name)) set.delete(name);
    else set.add(name);
    emit(set);
  };

  const groups = GROUP_ORDER.map((group) => ({
    group,
    items: tools.filter((t) => metaFor(t.name).group === group),
  })).filter((g) => g.items.length > 0);

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        type="button"
        className={open ? "btn xs active" : "btn xs"}
        disabled={disabled}
        title={t("tools.menuTitle", {
          enabled: enabledCount,
          total: names.length,
        })}
        onClick={() => {
          setOpen((v) => !v);
        }}
      >
        <SlidersHorizontal size={12} />
        <span className="dim">
          {enabledCount}/{names.length}
        </span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            right: 0,
            width: 280,
            maxHeight: 360,
            overflowY: "auto",
            zIndex: 50,
            padding: 8,
            background: "var(--bg-1)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-2, 8px)",
            boxShadow: "var(--shadow-elev, 0 8px 24px rgba(0,0,0,0.3))",
          }}
        >
          <div
            className="flex items-center justify-between"
            style={{ padding: "2px 4px 8px" }}
          >
            <span style={{ fontSize: 12, fontWeight: 600 }}>
              {t("tools.heading")}
            </span>
            <div className="flex items-center" style={{ gap: 6 }}>
              <button
                type="button"
                className="btn xs ghost"
                onClick={() => {
                  onChange(null);
                }}
              >
                {t("tools.all")}
              </button>
              <button
                type="button"
                className="btn xs ghost"
                onClick={() => {
                  onChange([]);
                }}
              >
                {t("tools.none")}
              </button>
            </div>
          </div>

          {groups.map(({ group, items }) => (
            <div key={group} style={{ marginBottom: 6 }}>
              <div
                className="dim"
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: 0.4,
                  padding: "4px 4px 2px",
                }}
              >
                {t(GROUP_LABEL_KEY[group] ?? "tools.groupOther")}
              </div>
              {items.map((tool) => {
                const meta = metaFor(tool.name);
                return (
                  <label
                    key={tool.name}
                    className="flex items-center"
                    style={{
                      gap: 8,
                      padding: "5px 6px",
                      borderRadius: 6,
                      cursor: "pointer",
                      fontSize: 12.5,
                    }}
                    title={tool.description}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = "var(--bg-hover)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = "transparent";
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isOn(tool.name)}
                      onChange={() => {
                        toggle(tool.name);
                      }}
                      style={{ flexShrink: 0 }}
                    />
                    <span style={{ minWidth: 0 }} className="truncate">
                      {meta.labelKey ? t(meta.labelKey) : tool.name}
                    </span>
                  </label>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
