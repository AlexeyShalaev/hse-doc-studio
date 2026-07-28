import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  Bot,
  FileText,
  FolderOpen,
  Grid3x3,
  History,
  ListChecks,
  Monitor,
  Moon,
  Plus,
  Search,
  Settings,
  Sun,
  Terminal,
  type LucideIcon,
} from "lucide-react";
import { useProjects } from "@entities/project";
import { useThemeStore, useUIStore, useWorkspaceStore } from "@shared/lib";

type Command = {
  id: string;
  label: string;
  icon: LucideIcon;
  shortcut?: string;
  run: () => void;
};

export const CommandPalette = () => {
  const { t } = useTranslation("appChrome");
  const navigate = useNavigate();
  const params = useParams<{ projectId?: string; docId?: string }>();
  const isOpen = useUIStore((s) => s.paletteOpen);
  const setOpen = useUIStore((s) => s.setPaletteOpen);
  const togglePalette = useUIStore((s) => s.togglePaletteOpen);
  const setTheme = useThemeStore((s) => s.setTheme);
  const setSystemChatOpen = useWorkspaceStore((s) => s.setSystemChatOpen);
  const { data: projects } = useProjects();

  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        togglePalette();
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
        const target = e.target as HTMLElement | null;
        const isEditable =
          target &&
          (target.tagName === "INPUT" ||
            target.tagName === "TEXTAREA" ||
            target.isContentEditable);
        if (!isEditable) {
          e.preventDefault();
          setOpen(false);
          void navigate("/wizard?mode=create");
        }
      }
      if ((e.metaKey || e.ctrlKey) && e.key === ",") {
        e.preventDefault();
        setOpen(false);
        void navigate("/settings");
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [togglePalette, setOpen, navigate]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const t = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
    return () => {
      clearTimeout(t);
    };
  }, [isOpen]);

  const handleOpenChange = (open: boolean) => {
    setOpen(open);
    if (!open) setQuery("");
  };

  const commands: Command[] = useMemo(() => {
    const base: Command[] = [
      {
        id: "new",
        label: t("commandPalette.newProject"),
        icon: Plus,
        shortcut: "⌘N",
        run: () => {
          setOpen(false);
          void navigate("/wizard?mode=create");
        },
      },
      {
        id: "settings",
        label: t("commandPalette.settings"),
        icon: Settings,
        shortcut: "⌘,",
        run: () => {
          setOpen(false);
          void navigate("/settings");
        },
      },
      {
        id: "theme-system",
        label: t("commandPalette.themeSystem"),
        icon: Monitor,
        run: () => {
          setTheme("system");
          setOpen(false);
        },
      },
      {
        id: "theme-dark",
        label: t("commandPalette.themeDark"),
        icon: Moon,
        run: () => {
          setTheme("dark");
          setOpen(false);
        },
      },
      {
        id: "theme-light",
        label: t("commandPalette.themeLight"),
        icon: Sun,
        run: () => {
          setTheme("light");
          setOpen(false);
        },
      },
      {
        id: "theme-blueprint",
        label: t("commandPalette.themeBlueprint"),
        icon: Grid3x3,
        run: () => {
          setTheme("blueprint");
          setOpen(false);
        },
      },
      {
        id: "agent",
        label: t("commandPalette.callAgent"),
        icon: Bot,
        run: () => {
          setSystemChatOpen(true);
          setOpen(false);
        },
      },
    ];

    // Context commands for the currently open document (jump to its tabs).
    const { projectId, docId } = params;
    const docCmds: Command[] =
      projectId && docId
        ? (
            [
              {
                id: "doc-preview",
                label: t("commandPalette.docPreview"),
                icon: FileText,
                tab: "",
              },
              {
                id: "doc-checks",
                label: t("commandPalette.docChecks"),
                icon: ListChecks,
                tab: "checks",
              },
              {
                id: "doc-compile",
                label: t("commandPalette.docCompile"),
                icon: Terminal,
                tab: "compile",
              },
              {
                id: "doc-history",
                label: t("commandPalette.docHistory"),
                icon: History,
                tab: "history",
              },
            ] as const
          ).map((c) => ({
            id: c.id,
            label: c.label,
            icon: c.icon,
            run: () => {
              setOpen(false);
              const suffix = c.tab ? `?tab=${c.tab}` : "";
              void navigate(
                `/projects/${projectId}/documents/${docId}${suffix}`,
              );
            },
          }))
        : [];

    const projectCmds: Command[] = (projects ?? [])
      .filter((p) => !p.archived)
      .map((p) => ({
        id: `proj-${p.id}`,
        label: t("commandPalette.openProject", { name: p.name }),
        icon: FolderOpen,
        run: () => {
          setOpen(false);
          void navigate(`/projects/${p.id}/documents`);
        },
      }));

    return [...base, ...docCmds, ...projectCmds];
  }, [navigate, params, projects, setOpen, setTheme, setSystemChatOpen, t]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  return (
    <DialogPrimitive.Root open={isOpen} onOpenChange={handleOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="scrim" />
        <DialogPrimitive.Content
          className="modal-panel fixed left-1/2 top-1/3 z-[101] -translate-x-1/2 -translate-y-1/2"
          style={{ width: 520, maxWidth: "calc(100vw - 32px)" }}
        >
          <DialogPrimitive.Title className="sr-only">
            {t("commandPalette.title")}
          </DialogPrimitive.Title>
          <div
            className="flex items-center"
            style={{
              padding: "10px 14px",
              borderBottom: "1px solid var(--border)",
              gap: 10,
            }}
          >
            <Search size={14} style={{ color: "var(--fg-2)" }} />
            <input
              ref={inputRef}
              className="flex-1 bg-transparent outline-none text-fg-0"
              style={{
                fontSize: 13,
                border: 0,
                padding: 0,
              }}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
              placeholder={t("commandPalette.placeholder")}
            />
            <span className="kbd">ESC</span>
          </div>
          <div
            style={{
              maxHeight: 360,
              overflowY: "auto",
              padding: 6,
            }}
          >
            {filtered.length === 0 ? (
              <div className="dim" style={{ padding: 16, textAlign: "center" }}>
                {t("commandPalette.empty")}
              </div>
            ) : (
              filtered.map((c) => {
                const Icon = c.icon;
                return (
                  <button
                    key={c.id}
                    type="button"
                    className="row-btn"
                    onClick={c.run}
                  >
                    <Icon size={14} style={{ color: "var(--fg-2)" }} />
                    <span className="flex-1">{c.label}</span>
                    {c.shortcut && <span className="kbd">{c.shortcut}</span>}
                  </button>
                );
              })
            )}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
