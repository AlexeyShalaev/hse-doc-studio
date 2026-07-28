import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useNavigate } from "react-router";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { useDebouncedCallback } from "use-debounce";
import { clsx } from "clsx";
import {
  documentKeys,
  useCheckResults,
  fetchFileWithVersion,
  fileKeys,
  StaleFileError,
  useFile,
  useFiles,
  useFileVersion,
  useFileWithVersion,
  usePutFile,
  useUploadFile,
} from "@entities/document";
import { apiClient } from "@shared/api/client";
import { synctexApi } from "@entities/synctex";
import { toast, useEditorPrefsStore, useSyncTexStore } from "@shared/lib";
import {
  CodeEditor,
  Spinner,
  type CodeEditorController,
  type DiagnosticClickInfo,
  type EditorDiagnostic,
  type EditorFormatState,
  type EditorStats,
  type OutlineState,
  type RevealRequest,
  type VisualEmbeddedInputKind,
} from "@shared/ui";
import { applyQuickFix } from "../lib/applyQuickFix";
import { findingsToDiagnostics } from "../lib/findingsToDiagnostics";
import { insertSuppression } from "../lib/insertSuppression";
import { languageForPath } from "../lib/languageForPath";
import {
  parseMacroDefinitions,
  resolveMacroAliases,
} from "../lib/parseMacroDefinitions";
import {
  findLatexInputTargets,
  parseHeadingStyles,
} from "../lib/parseHeadingStyles";
import { resolveDocRelativePath } from "../lib/resolveDocRelativePath";
import {
  DiagnosticActionMenu,
  type DiagnosticActions,
} from "./DiagnosticActionMenu";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { BibliographyEditorModal } from "./BibliographyEditorModal";
import { FormatToolbar } from "./FormatToolbar";
import { OutlinePanel } from "./OutlinePanel";
import { ExternalChangeBanner } from "./ExternalChangeBanner";
import { SourceEditorToolbar, type SaveStatus } from "./SourceEditorToolbar";
import { TableEditorModal } from "./TableEditorModal";

const AUTOSAVE_DELAY_MS = 1200;
// Сколько держать отметку «подтянуто снаружи» после молчаливого обновления.
const EXTERNAL_UPDATE_NOTICE_MS = 4000;
const DRAFT_KEY_PREFIX = "hse-draft:";
// Pack conventions surfaced in the visual mode (module-level for stable
// identities in the visualOptions memo).
const HINT_PREFIXES = ["Подсказка:"];
const HIGHLIGHT_ENVS = ["hseExample"];
const KNOWN_EMBEDDED_INPUT_KINDS: Readonly<
  Record<string, VisualEmbeddedInputKind>
> = {
  title_template: "titlePages",
  title: "vkrTitle",
  requirements_table: "requirementsTable",
  change_log: "changeLog",
};
const NON_PRINTING_INPUT_BASENAMES = new Set([
  "commands",
  "fonts",
  "meta",
  "preamble",
  "styles",
]);
const NON_PROSE_TEX_FILES = new Set([
  "commands.tex",
  "fonts.tex",
  "preamble.tex",
  "styles.tex",
]);
// Compile-safe image formats for the pack's xelatex toolchain.
const MIME_TO_EXT: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/bmp": "bmp",
};

type VisualCanvasStyle = CSSProperties & {
  "--visual-font-size": string;
  "--visual-page-width": string;
  "--visual-page-pad-x": string;
  "--visual-page-pad-top": string;
  "--visual-page-pad-bottom": string;
};

const draftKeyFor = (projectId: string, path: string): string =>
  `${DRAFT_KEY_PREFIX}${projectId}:${path}`;

const withDefaultTexExtension = (path: string): string =>
  /(?:^|\/)[^/]+\.[^/]+$/.test(path) ? path : `${path}.tex`;

const latexInputBasename = (path: string): string =>
  (path.replace(/\\/g, "/").split("/").pop() ?? path)
    .replace(/\.tex$/i, "")
    .toLocaleLowerCase();

const classifyEmbeddedInput = (
  basename: string,
  source: string | undefined,
): VisualEmbeddedInputKind => {
  // Source signatures keep renamed pack fragments useful and prevent an
  // unrelated user file named `title.tex` from receiving a false preview.
  if (source !== undefined) {
    if (
      source.includes("\\begin{titlepage}") &&
      /Выпускная\s+квалификационная\s+работа/i.test(source)
    ) {
      return "vkrTitle";
    }
    if (/ЛИСТ\s+УТВЕРЖДЕНИЯ/i.test(source) && /\\doccodelu\b/.test(source)) {
      return "titlePages";
    }
    if (source.includes("\\begin{longtable}") && /\\req\s*\{/.test(source)) {
      return "requirementsTable";
    }
    if (/ЛИСТ\s+РЕГИСТРАЦИИ\s+ИЗМЕНЕНИЙ/i.test(source)) {
      return "changeLog";
    }
    return "generic";
  }
  return KNOWN_EMBEDDED_INPUT_KINDS[basename] ?? "generic";
};

const parseDocumentMacros = (source: string): Record<string, string> => {
  const documentStart = source.indexOf("\\begin{document}");
  return parseMacroDefinitions(
    documentStart < 0 ? source : source.slice(0, documentStart),
  );
};

const readDraft = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const writeDraft = (key: string, text: string): void => {
  try {
    localStorage.setItem(key, text);
  } catch {
    // Quota or privacy mode — draft recovery is best-effort.
  }
};

const clearDraft = (key: string): void => {
  try {
    localStorage.removeItem(key);
  } catch {
    // ignore
  }
};

export type SourceEditorProps = {
  projectId: string;
  relativePath: string;
  /** When set, this file's check findings drive the gutter/inline markers. */
  docId?: string;
  /**
   * Pre-computed diagnostics (e.g. from the project-wide aggregation in the
   * file explorer). Takes precedence over the `docId`-derived findings.
   */
  diagnostics?: EditorDiagnostic[];
  /** When set, clicking a finding inline opens a menu with these actions. */
  diagnosticActions?: DiagnosticActions;
  /** Generated/derived files (e.g. common/meta.tex) open read-only. */
  readOnly?: boolean;
  readOnlyReason?: string;
  /** One-shot: scroll to this 1-based line (e.g. a click from «Проверки»). */
  revealLine?: number;
  onRevealConsumed?: () => void;
};

type SourceEditorBodyProps = SourceEditorProps & {
  initialValue: string;
  // Версия, на которой открыли файл: с ней уходит `If-Match` при сохранении.
  initialEtag: string | null;
};

const SourceEditorBody = ({
  projectId,
  relativePath,
  docId,
  diagnostics: diagnosticsOverride,
  diagnosticActions,
  readOnly = false,
  readOnlyReason,
  revealLine,
  onRevealConsumed,
  initialValue,
  initialEtag,
}: SourceEditorBodyProps) => {
  const { t } = useTranslation("sourceEdit");
  const { mutateAsync: putFile } = usePutFile();
  const { data: checks } = useCheckResults(projectId, docId ?? "");
  const queryClient = useQueryClient();

  const draftKey = draftKeyFor(projectId, relativePath);

  // Draft recovery: open with an unsaved draft from a previous session if it
  // differs from on-disk content (the user's last in-editor work), flagged
  // dirty so the banner can offer reverting to the saved version.
  const [bootValue] = useState(() => {
    if (readOnly) return initialValue;
    const raw = readDraft(draftKey);
    return raw != null && raw !== initialValue ? raw : initialValue;
  });
  const [latexInputTargets, setLatexInputTargets] = useState(() =>
    findLatexInputTargets(bootValue),
  );
  const latexInputSignatureRef = useRef(JSON.stringify(latexInputTargets));
  const [documentMacros, setDocumentMacros] = useState(() =>
    parseDocumentMacros(bootValue),
  );
  const documentMacrosSignatureRef = useRef(JSON.stringify(documentMacros));
  // `editorValue` is normally static (the editor is the source of truth while
  // open); it only changes to force a revert-to-saved. `savedRef` tracks the
  // on-disk content so dirty state is computed against disk, not the draft.
  const [editorValue, setEditorValue] = useState(bootValue);
  const valueRef = useRef(bootValue);
  const savedRef = useRef(initialValue);
  // Версия `savedRef.current` на диске. Обновляется вместе с ним — по ней
  // бэкенд отличает «я пишу поверх того, что видел» от «файл успели поправить».
  const savedEtagRef = useRef(initialEtag);
  // Непустое — файл разошёлся с диском: автосохранение остановлено до выбора.
  const [conflict, setConflict] = useState<{
    diskContent: string;
    diskEtag: string;
  } | null>(null);
  // Ненавязчивая отметка «подтянуто снаружи» для чистого буфера.
  const [externallyUpdated, setExternallyUpdated] = useState(false);
  const [recovered, setRecovered] = useState(() => bootValue !== initialValue);
  const [stats, setStats] = useState<EditorStats | null>(null);
  const [status, setStatus] = useState<SaveStatus>(
    bootValue !== initialValue ? "dirty" : "saved",
  );
  const [wrapLines, setWrapLines] = useState(false);
  const [inlineDiagnostics, setInlineDiagnostics] = useState(true);
  const [panelOpen, setPanelOpen] = useState(false);

  // «Код | Визуальный»: sticky global preference; the visual mode only makes
  // sense for LaTeX documents (never .bib/.md or style files).
  const language = languageForPath(relativePath);
  const pathParts = relativePath.toLowerCase().split("/");
  const sourceFileName = pathParts.at(-1) ?? "";
  const visualEligible =
    language === "latex" &&
    sourceFileName.endsWith(".tex") &&
    !pathParts.includes("common") &&
    !NON_PROSE_TEX_FILES.has(sourceFileName);
  const sourceMode = useEditorPrefsStore((s) => s.sourceMode);
  const setSourceMode = useEditorPrefsStore((s) => s.setSourceMode);
  const showComments = useEditorPrefsStore((s) => s.showComments);
  const showOutline = useEditorPrefsStore((s) => s.showOutline);
  const visualZoom = useEditorPrefsStore((s) => s.visualZoom);
  const visualMode = visualEligible && sourceMode === "visual";
  const controllerRef = useRef<CodeEditorController | null>(null);
  const [focusMode, setFocusMode] = useState(false);

  // A pane-local "focus" action becomes a true distraction-free writing
  // surface by covering the workspace chrome. Escape exits focus first, or
  // closes the navigation pane when focus is not active.
  useEffect(() => {
    if (!focusMode && !showOutline) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        if (focusMode) {
          setFocusMode(false);
        } else if (showOutline) {
          useEditorPrefsStore.getState().toggleShowOutline();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [focusMode, showOutline]);

  const visualCanvasStyle = useMemo<VisualCanvasStyle>(() => {
    const scale = visualZoom / 100;
    return {
      "--visual-font-size": `${String(15.5 * scale)}px`,
      "--visual-page-width": `${String(816 * scale)}px`,
      "--visual-page-pad-x": `${String(72 * scale)}px`,
      "--visual-page-pad-top": `${String(64 * scale)}px`,
      "--visual-page-pad-bottom": `${String(96 * scale)}px`,
    };
  }, [visualZoom]);

  // Project macro values (\hseProjectName → «…») for Word-style fields in the
  // visual mode. An empty path disables the query; a missing file is fine.
  const { data: metaTex } = useFile(
    projectId,
    visualEligible ? "common/meta.tex" : "",
  );
  const { data: commandsTex } = useFile(
    projectId,
    visualEligible ? "common/commands.tex" : "",
  );
  const headingStylePaths = useMemo(
    () =>
      visualEligible
        ? latexInputTargets
            .filter((target) => {
              const basename = latexInputBasename(target);
              return basename === "preamble" || basename === "styles";
            })
            .map((target) => resolveDocRelativePath(relativePath, target))
            .filter((path): path is string => path !== null)
            .map(withDefaultTexExtension)
        : [],
    [latexInputTargets, relativePath, visualEligible],
  );
  const { data: headingStyleTex1 } = useFile(
    projectId,
    headingStylePaths[0] ?? "",
  );
  const { data: headingStyleTex2 } = useFile(
    projectId,
    headingStylePaths[1] ?? "",
  );
  const embeddedInputBindings = useMemo(
    () =>
      visualEligible
        ? latexInputTargets
            .map((target) => ({
              target,
              basename: latexInputBasename(target),
              resolvedPath: resolveDocRelativePath(relativePath, target),
            }))
            .filter(
              ({ basename }) => !NON_PRINTING_INPUT_BASENAMES.has(basename),
            )
        : [],
    [latexInputTargets, relativePath, visualEligible],
  );
  const embeddedInputPaths = useMemo(
    () => [
      ...new Set(
        embeddedInputBindings
          .map(({ resolvedPath }) => resolvedPath)
          .filter((path): path is string => path !== null)
          .map(withDefaultTexExtension),
      ),
    ],
    [embeddedInputBindings],
  );
  const embeddedInputFiles = useFiles(projectId, embeddedInputPaths);
  const embeddedInputConfig = useMemo(() => {
    const basenames: string[] = [];
    const kinds: Record<string, VisualEmbeddedInputKind> = {};
    const sources: Record<string, string> = {};

    for (const binding of embeddedInputBindings) {
      const resolvedPath = binding.resolvedPath
        ? withDefaultTexExtension(binding.resolvedPath)
        : null;
      const source = resolvedPath
        ? embeddedInputFiles[resolvedPath]
        : undefined;
      const kind = classifyEmbeddedInput(binding.basename, source);
      basenames.push(binding.basename);
      kinds[binding.target] = kind;
      kinds[binding.basename] ??= kind;
      if (source !== undefined) {
        sources[binding.target] = source;
        sources[binding.basename] ??= source;
      }
    }

    return {
      basenames: [...new Set(basenames)],
      kinds,
      sources,
    };
  }, [embeddedInputBindings, embeddedInputFiles]);
  const visualOptions = useMemo(
    () => ({
      macros: resolveMacroAliases({
        ...parseMacroDefinitions(commandsTex ?? ""),
        ...parseMacroDefinitions(metaTex ?? ""),
        ...documentMacros,
      }),
      showComments,
      hintPrefixes: HINT_PREFIXES,
      highlightEnvs: HIGHLIGHT_ENVS,
      headingAlignments: parseHeadingStyles(
        [headingStyleTex1, headingStyleTex2]
          .filter((source): source is string => source !== undefined)
          .join("\n"),
      ),
      embeddedInputBasenames: embeddedInputConfig.basenames,
      embeddedInputKinds: embeddedInputConfig.kinds,
      embeddedInputSources: embeddedInputConfig.sources,
    }),
    [
      metaTex,
      commandsTex,
      headingStyleTex1,
      headingStyleTex2,
      embeddedInputConfig,
      documentMacros,
      showComments,
    ],
  );
  const [formatState, setFormatState] = useState<EditorFormatState | null>(
    null,
  );
  const [outline, setOutline] = useState<OutlineState | null>(null);
  const handlePasteTransformed = useCallback(() => {
    toast.info(t("paste.escaped"));
  }, [t]);

  // Inline image previews: resolve `\includegraphics{…}` paths (relative to
  // this document's directory) to the backend's file endpoint.
  const resolveAssetUrl = useCallback(
    (target: string): string | null => {
      if (!/\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(target)) return null;
      const resolved = resolveDocRelativePath(relativePath, target);
      if (!resolved) return null;
      return `${apiClient.defaults.baseURL ?? ""}/projects/${projectId}/files/${encodeURIComponent(resolved)}`;
    },
    [relativePath, projectId],
  );

  // Pasted/dropped image → upload into `<docDir>/img/` → the editor inserts
  // a figure snippet with the returned (doc-relative) path.
  const { mutateAsync: uploadFile } = useUploadFile();
  const handleDropImage = useCallback(
    async (file: File): Promise<string | null> => {
      try {
        const extFromName = /\.([A-Za-z0-9]+)$/.exec(file.name)?.[1];
        const ext = (
          extFromName ??
          MIME_TO_EXT[file.type] ??
          "png"
        ).toLowerCase();
        // Millisecond stamp + random suffix — two pastes within the same
        // second must never silently overwrite each other.
        const stamp = new Date()
          .toISOString()
          .slice(0, 23)
          .replace(/[-:.]/g, "")
          .replace("T", "-");
        const unique = Math.random().toString(36).slice(2, 6);
        const docRelative = `img/paste-${stamp}-${unique}.${ext}`;
        const docDir = relativePath.split("/").slice(0, -1).join("/");
        const projectPath = docDir ? `${docDir}/${docRelative}` : docRelative;
        await uploadFile({
          projectId,
          path: projectPath,
          data: await file.arrayBuffer(),
          contentType: file.type || "application/octet-stream",
        });
        toast.success(t("paste.imageUploaded", { path: projectPath }));
        return docRelative;
      } catch {
        toast.error(t("paste.imageFailed"));
        return null;
      }
    },
    [relativePath, projectId, uploadFile, t],
  );
  const handleImageInsertSkipped = useCallback(() => {
    toast.info(t("paste.imageInsertSkipped"));
  }, [t]);

  // Click on an `\input{…}` chip → open the referenced file in «Файлы
  // проекта» (paths resolve against this document's directory).
  const navigate = useNavigate();
  const handleOpenFile = useCallback(
    (target: string) => {
      const resolved = resolveDocRelativePath(relativePath, target);
      if (!resolved) {
        toast.info(t("editor.openFileFailed", { path: target }));
        return;
      }
      const resolvedFile = withDefaultTexExtension(resolved);
      void navigate(
        `/projects/${projectId}/files?file=${encodeURIComponent(resolvedFile)}`,
      );
    },
    [relativePath, projectId, navigate, t],
  );
  const [reveal, setReveal] = useState<RevealRequest | undefined>(undefined);
  // Structured table editor: the visual table card opens it with the table's
  // raw LaTeX and a `commit` that writes the regenerated source back.
  const [tableEditor, setTableEditor] = useState<{
    source: string;
    commit: (next: string) => void;
  } | null>(null);
  const handleEditTable = useCallback(
    (source: string, commit: (next: string) => void) => {
      setTableEditor({ source, commit });
    },
    [],
  );
  // Structured bibliography manager: opened from the inline list's «Управлять» /
  // «Добавить», with the env's raw LaTeX and a `commit` that writes it back.
  const [bibliographyEditor, setBibliographyEditor] = useState<{
    source: string;
    commit: (next: string) => void;
  } | null>(null);
  const handleEditBibliography = useCallback(
    (source: string, commit: (next: string) => void) => {
      setBibliographyEditor({ source, commit });
    },
    [],
  );
  const [menu, setMenu] = useState<{
    left: number;
    top: number;
    items: EditorDiagnostic[];
  } | null>(null);
  const tokenRef = useRef(0);
  const currentLineRef = useRef<number | null>(null);

  const diagnostics = useMemo(
    () =>
      diagnosticsOverride ??
      findingsToDiagnostics(
        checks?.results,
        relativePath,
        diagnosticActions?.severityOverride,
      ),
    [
      diagnosticsOverride,
      checks,
      relativePath,
      diagnosticActions?.severityOverride,
    ],
  );

  const counts = useMemo(() => {
    let error = 0;
    let warning = 0;
    let info = 0;
    for (const d of diagnostics) {
      if (d.severity === "error") error += 1;
      else if (d.severity === "warning") warning += 1;
      else info += 1;
    }
    return { error, warning, info };
  }, [diagnostics]);

  const sortedLines = useMemo(
    () => [...new Set(diagnostics.map((d) => d.line))].sort((a, b) => a - b),
    [diagnostics],
  );

  const gotoLine = useCallback((line: number) => {
    currentLineRef.current = line;
    tokenRef.current += 1;
    setReveal({ line, token: tokenRef.current });
  }, []);

  // ── SyncTeX forward (Ctrl/Cmd+click in source → jump to the spot in the PDF)
  const requestPdfJump = useSyncTexStore((s) => s.requestPdfJump);
  const sourceJump = useSyncTexStore((s) => s.sourceJump);
  const consumedJumpRef = useRef(0);

  const handleModClick = useCallback(
    (line: number) => {
      if (!docId) return;
      void synctexApi
        .forward(projectId, docId, relativePath, line)
        .then((r) => {
          const b = r.boxes[0];
          if (b) {
            requestPdfJump({
              page: b.page,
              xPt: b.x,
              yPt: b.y,
              widthPt: b.width,
              heightPt: b.height,
            });
          } else {
            toast.info(t("syncTex.noPdfPosition"));
          }
        })
        .catch(() => {
          toast.warning(t("syncTex.unavailable"));
        });
    },
    [docId, projectId, relativePath, requestPdfJump, t],
  );

  // ── SyncTeX inverse (a PDF click resolved to this file → scroll to the line)
  useEffect(() => {
    if (!sourceJump || sourceJump.token === consumedJumpRef.current) return;
    const base = (p: string): string => p.split("/").pop() ?? p;
    if (base(sourceJump.file) === base(relativePath)) {
      consumedJumpRef.current = sourceJump.token;
      gotoLine(sourceJump.line);
    }
  }, [sourceJump, relativePath, gotoLine]);

  // ── "Find in source" (selected PDF text → locate the line that produced it).
  // PDF text differs from source in whitespace/line-breaks, so we match the
  // first few words allowing any whitespace between them.
  const sourceFind = useSyncTexStore((s) => s.sourceFind);
  const consumedFindRef = useRef(0);
  useEffect(() => {
    if (!sourceFind || sourceFind.token === consumedFindRef.current) return;
    consumedFindRef.current = sourceFind.token;
    const words = sourceFind.text
      .trim()
      .split(/\s+/)
      .slice(0, 8)
      .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .filter(Boolean);
    if (words.length === 0) return;
    try {
      const re = new RegExp(words.join("\\s+"), "i");
      const m = re.exec(valueRef.current);
      if (m) gotoLine(valueRef.current.slice(0, m.index).split("\n").length);
      else toast.info(t("find.notFound"));
    } catch {
      toast.info(t("find.notFound"));
    }
  }, [sourceFind, gotoLine, t]);

  const gotoNext = useCallback(() => {
    if (sortedLines.length === 0) return;
    const cur = currentLineRef.current;
    const next =
      (cur == null ? undefined : sortedLines.find((l) => l > cur)) ??
      sortedLines[0];
    if (next != null) gotoLine(next);
  }, [sortedLines, gotoLine]);

  const gotoPrev = useCallback(() => {
    if (sortedLines.length === 0) return;
    const cur = currentLineRef.current;
    const earlier =
      cur == null ? sortedLines : sortedLines.filter((l) => l < cur);
    const target =
      earlier.length > 0
        ? earlier[earlier.length - 1]
        : sortedLines[sortedLines.length - 1];
    if (target != null) gotoLine(target);
  }, [sortedLines, gotoLine]);

  const handleDiagnosticClick = (info: DiagnosticClickInfo): void => {
    const items = diagnostics.filter((d) => d.line === info.line);
    if (items.length > 0) {
      setMenu({ left: info.left, top: info.bottom, items });
    }
  };

  // Deterministic quick-fix: apply the substitution client-side (instant, no
  // round-trip) by pushing new content into the editor, which autosaves.
  const handleApplyFix = useCallback((d: EditorDiagnostic) => {
    if (!d.fix) return;
    const next = applyQuickFix(valueRef.current, d.fix);
    if (next == null || next === valueRef.current) return;
    valueRef.current = next;
    setEditorValue(next);
  }, []);

  // External one-shot reveal (e.g. a finding clicked in the «Проверки» tab).
  useEffect(() => {
    if (typeof revealLine === "number" && Number.isFinite(revealLine)) {
      gotoLine(revealLine);
      onRevealConsumed?.();
    }
  }, [revealLine, gotoLine, onRevealConsumed]);

  const save = useCallback(
    async (text: string, overrideEtag?: string) => {
      if (readOnly) return;
      setStatus("saving");
      try {
        const { etag } = await putFile({
          projectId,
          path: relativePath,
          content: text,
          ifMatch: overrideEtag ?? savedEtagRef.current,
        });
        savedRef.current = text;
        savedEtagRef.current = etag;
        setConflict(null);
        clearDraft(draftKey);
        setRecovered(false);
        setStatus(valueRef.current === text ? "saved" : "dirty");
      } catch (error) {
        if (error instanceof StaleFileError) {
          // Файл поправили снаружи, пока мы печатали: не затираем — спрашиваем.
          setConflict({
            diskContent: error.diskContent,
            diskEtag: error.diskEtag,
          });
          setStatus("dirty");
          return;
        }
        setStatus("error");
      }
    },
    [projectId, relativePath, readOnly, putFile, draftKey],
  );

  const debouncedSave = useDebouncedCallback(
    (text: string) => void save(text),
    AUTOSAVE_DELAY_MS,
  );

  const handleChange = useCallback(
    (text: string) => {
      valueRef.current = text;
      if (visualEligible) {
        const nextTargets = findLatexInputTargets(text);
        const nextSignature = JSON.stringify(nextTargets);
        if (nextSignature !== latexInputSignatureRef.current) {
          latexInputSignatureRef.current = nextSignature;
          setLatexInputTargets(nextTargets);
        }
        const nextMacros = parseDocumentMacros(text);
        const nextMacroSignature = JSON.stringify(nextMacros);
        if (nextMacroSignature !== documentMacrosSignatureRef.current) {
          documentMacrosSignatureRef.current = nextMacroSignature;
          setDocumentMacros(nextMacros);
        }
      }
      if (readOnly) return;
      if (text === savedRef.current) {
        debouncedSave.cancel();
        clearDraft(draftKey);
        setRecovered(false);
        setStatus("saved");
      } else {
        writeDraft(draftKey, text);
        setStatus("dirty");
        // Пока конфликт не разрешён, на диск не пишем ничего: любая запись
        // означала бы молчаливый выбор за пользователя.
        if (!conflict) debouncedSave(text);
      }
    },
    [readOnly, debouncedSave, draftKey, visualEligible, conflict],
  );

  const handleSave = useCallback(() => {
    debouncedSave.cancel();
    void save(valueRef.current);
  }, [debouncedSave, save]);

  // ── синхронизация с внешними правками ───────────────────────────────────
  // Тот же файл открыт в VS Code — опрашиваем его версию. Слежение за ФС здесь
  // не годится: события inotify не переходят границу бинд-маунта контейнера.
  const { data: diskVersion } = useFileVersion(projectId, relativePath, {
    enabled: !readOnly && !conflict,
  });

  const applyDiskContent = useCallback(
    (content: string, etag: string | null) => {
      debouncedSave.cancel();
      savedRef.current = content;
      savedEtagRef.current = etag;
      valueRef.current = content;
      setEditorValue(content);
      clearDraft(draftKey);
      setRecovered(false);
      setConflict(null);
      setStatus("saved");
    },
    [debouncedSave, draftKey],
  );

  useEffect(() => {
    const etag = diskVersion?.etag;
    // Своя же запись поднимает версию — реагируем только на чужую.
    if (!etag || etag === savedEtagRef.current || conflict) return;

    let cancelled = false;
    void queryClient
      .fetchQuery({
        queryKey: fileKeys.content(projectId, relativePath),
        queryFn: () => fetchFileWithVersion(projectId, relativePath),
        staleTime: 0,
      })
      .then((fresh) => {
        if (cancelled || fresh.etag === savedEtagRef.current) return;
        const dirty = valueRef.current !== savedRef.current;
        if (!dirty) {
          // Терять нечего — подхватываем молча, как это делают VS Code и IDEA.
          applyDiskContent(fresh.content, fresh.etag);
          setExternallyUpdated(true);
          return;
        }
        setConflict({ diskContent: fresh.content, diskEtag: fresh.etag ?? "" });
      })
      .catch(() => {
        // Файл мог исчезнуть; следующий опрос покажет это честнее, чем баннер.
      });
    return () => {
      cancelled = true;
    };
  }, [
    diskVersion?.etag,
    conflict,
    projectId,
    relativePath,
    queryClient,
    applyDiskContent,
  ]);

  // Отметка «обновлено извне» живёт до первой правки пользователя.
  useEffect(() => {
    if (!externallyUpdated) return;
    const timer = setTimeout(() => {
      setExternallyUpdated(false);
    }, EXTERNAL_UPDATE_NOTICE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [externallyUpdated]);

  const takeDiskVersion = useCallback(() => {
    if (conflict) applyDiskContent(conflict.diskContent, conflict.diskEtag);
  }, [conflict, applyDiskContent]);

  const keepMyVersion = useCallback(() => {
    if (!conflict) return;
    // Перезаписываем осознанно: `If-Match` — уже дисковая версия, поэтому
    // бэкенд пропустит запись, а не отдаст 409 снова.
    void save(valueRef.current, conflict.diskEtag);
  }, [conflict, save]);

  // Revert an open draft to the on-disk version: push disk content into the
  // editor (the only place `editorValue` changes identity) and drop the draft.
  const revertToSaved = useCallback(() => {
    debouncedSave.cancel();
    valueRef.current = savedRef.current;
    setEditorValue(savedRef.current);
    clearDraft(draftKey);
    setRecovered(false);
    setStatus("saved");
  }, [debouncedSave, draftKey]);

  // Ignore one occurrence: append a `% hse-noqa: <rule>` comment to its line.
  // The backend drops the finding on read once the source is saved, so we
  // persist immediately and refresh the findings — without disabling the rule.
  const handleIgnoreFinding = useCallback(
    (d: EditorDiagnostic) => {
      const ruleId = d.source;
      if (!ruleId || readOnly) return;
      const next = insertSuppression(valueRef.current, d.line, ruleId);
      if (next === valueRef.current) return;
      const prevSaved = savedRef.current;
      valueRef.current = next;
      // Optimistic: matching savedRef stops the editor-sync from also autosaving.
      savedRef.current = next;
      debouncedSave.cancel();
      setEditorValue(next);
      setStatus("saving");
      void putFile({ projectId, path: relativePath, content: next })
        .then(() => {
          clearDraft(draftKey);
          setRecovered(false);
          setStatus("saved");
          void queryClient.invalidateQueries({
            queryKey: documentKeys.checkResults(projectId, docId ?? ""),
          });
        })
        .catch(() => {
          savedRef.current = prevSaved;
          setStatus("error");
        });
    },
    [
      readOnly,
      putFile,
      projectId,
      relativePath,
      draftKey,
      docId,
      queryClient,
      debouncedSave,
    ],
  );

  // Flush a pending autosave on unmount (e.g. switching files) so edits made
  // within the debounce window aren't silently dropped.
  useEffect(
    () => () => {
      debouncedSave.flush();
    },
    [debouncedSave],
  );

  const isDirty = status === "dirty" || status === "error";
  const hasDiagnostics = diagnostics.length > 0;

  return (
    <div
      className={clsx(
        "source-editor-root flex flex-col",
        visualMode && "is-visual",
        focusMode && "is-focus-mode",
      )}
      style={{
        flex: 1,
        minHeight: 0,
        background: "var(--bg-0)",
        ...visualCanvasStyle,
      }}
    >
      <SourceEditorToolbar
        relativePath={relativePath}
        readOnly={readOnly}
        readOnlyReason={readOnlyReason}
        status={status}
        counts={counts}
        modeAvailable={visualEligible}
        mode={visualMode ? "visual" : "code"}
        onModeChange={(mode) => {
          if (mode === "code") setFocusMode(false);
          setSourceMode(mode);
        }}
        wrapLines={wrapLines}
        onToggleWrap={() => {
          setWrapLines((w) => !w);
        }}
        inlineDiagnostics={inlineDiagnostics}
        onToggleInline={() => {
          setInlineDiagnostics((v) => !v);
        }}
        panelOpen={panelOpen}
        onTogglePanel={() => {
          setPanelOpen((v) => !v);
        }}
        onPrevProblem={gotoPrev}
        onNextProblem={gotoNext}
        isDirty={isDirty}
        onSave={handleSave}
        stats={stats}
      />

      {visualMode && (
        <FormatToolbar
          controller={controllerRef}
          formatState={formatState}
          readOnly={readOnly}
          focusMode={focusMode}
          onToggleFocusMode={() => {
            setFocusMode((value) => !value);
          }}
        />
      )}

      {externallyUpdated && !conflict && (
        <div
          className="flex items-center"
          style={{
            gap: 6,
            padding: "3px 12px",
            borderBottom: "1px solid var(--border)",
            fontSize: 11,
            color: "var(--fg-2)",
          }}
        >
          <RefreshCw size={11} />
          {t("externalChange.updatedExternally")}
        </div>
      )}

      {conflict && (
        <ExternalChangeBanner
          diskContent={conflict.diskContent}
          getBufferContent={() => valueRef.current}
          onTakeDisk={takeDiskVersion}
          onKeepMine={keepMyVersion}
          busy={status === "saving"}
        />
      )}

      {recovered && (
        <div
          className="flex items-center justify-between gap-3"
          style={{
            padding: "5px 12px",
            borderBottom: "1px solid var(--border)",
            background: "color-mix(in srgb, var(--c-warn) 14%, var(--bg-1))",
            fontSize: 11.5,
          }}
        >
          <span className="flex items-center gap-2">
            {t("recovery.message")}
          </span>
          <span className="flex items-center gap-2" style={{ flexShrink: 0 }}>
            <button type="button" className="btn xs" onClick={revertToSaved}>
              {t("recovery.revert")}
            </button>
            <button
              type="button"
              className="icon-btn sm"
              aria-label={t("recovery.hide")}
              onClick={() => {
                setRecovered(false);
              }}
            >
              ×
            </button>
          </span>
        </div>
      )}

      <div
        className="source-editor-layout flex"
        style={{ flex: 1, minHeight: 0, position: "relative" }}
      >
        {visualMode && showOutline && (
          <>
            <button
              type="button"
              className="visual-outline-backdrop"
              aria-label={t("outline.close")}
              onClick={() => {
                useEditorPrefsStore.getState().toggleShowOutline();
              }}
            />
            <OutlinePanel
              outline={outline}
              onSelect={gotoLine}
              onClose={() => {
                useEditorPrefsStore.getState().toggleShowOutline();
              }}
            />
          </>
        )}
        <div
          className="flex flex-col"
          style={{ flex: 1, minHeight: 0, minWidth: 0 }}
        >
          <CodeEditor
            value={editorValue}
            onChange={handleChange}
            onSave={handleSave}
            onStats={setStats}
            readOnly={readOnly}
            wrapLines={wrapLines}
            visualMode={visualMode}
            visualOptions={visualOptions}
            onFormatState={setFormatState}
            onOutline={setOutline}
            onPasteTransformed={handlePasteTransformed}
            onOpenFile={handleOpenFile}
            resolveAssetUrl={resolveAssetUrl}
            onDropImage={handleDropImage}
            onImageInsertSkipped={handleImageInsertSkipped}
            onEditTable={handleEditTable}
            onEditBibliography={handleEditBibliography}
            controllerRef={controllerRef}
            language={language}
            diagnostics={diagnostics}
            inlineDiagnostics={inlineDiagnostics}
            ariaLabel={t("editor.ariaLabel", { path: relativePath })}
            {...(visualMode ? { className: "visual-code-editor" } : {})}
            {...(reveal ? { reveal } : {})}
            {...(diagnosticActions
              ? { onDiagnosticClick: handleDiagnosticClick }
              : {})}
            {...(docId ? { onModClick: handleModClick } : {})}
          />
        </div>
      </div>

      {panelOpen && hasDiagnostics && (
        <DiagnosticsPanel
          diagnostics={diagnostics}
          activeLine={reveal?.line}
          onSelect={gotoLine}
          onClose={() => {
            setPanelOpen(false);
          }}
        />
      )}

      {menu && diagnosticActions && (
        <DiagnosticActionMenu
          left={menu.left}
          top={menu.top}
          items={menu.items}
          actions={{
            ...diagnosticActions,
            onApplyFix: handleApplyFix,
            onIgnoreFinding: handleIgnoreFinding,
          }}
          onClose={() => {
            setMenu(null);
          }}
        />
      )}

      <TableEditorModal
        isOpen={tableEditor != null}
        source={tableEditor?.source ?? ""}
        onSave={(next) => tableEditor?.commit(next)}
        onClose={() => {
          setTableEditor(null);
        }}
      />

      <BibliographyEditorModal
        isOpen={bibliographyEditor != null}
        source={bibliographyEditor?.source ?? ""}
        onSave={(next) => bibliographyEditor?.commit(next)}
        onClose={() => {
          setBibliographyEditor(null);
        }}
      />
    </div>
  );
};

/**
 * Connected source editor: loads the file, wires save (debounced autosave +
 * ⌘S), shows the document's check findings inline + in a panel, and supports
 * jump-to-line. Keyed by path so switching files reloads fresh content.
 */
export const SourceEditor = ({ relativePath, ...rest }: SourceEditorProps) => {
  const { t } = useTranslation("sourceEdit");
  const {
    data: file,
    isLoading,
    isError,
    error,
  } = useFileWithVersion(rest.projectId, relativePath);

  if (isLoading || file === undefined) {
    if (isError) {
      return (
        <div className="flex flex-1 items-center justify-center text-c-err text-sm">
          {t("editor.loadError", {
            detail: error instanceof Error ? error.message : relativePath,
          })}
        </div>
      );
    }
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <SourceEditorBody
      key={relativePath}
      relativePath={relativePath}
      initialValue={file.content}
      initialEtag={file.etag}
      {...rest}
    />
  );
};
