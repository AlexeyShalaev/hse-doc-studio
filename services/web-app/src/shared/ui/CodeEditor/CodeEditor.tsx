import { useEffect, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { redo, undo } from "@codemirror/commands";
import { clsx } from "clsx";
import {
  buildExtensions,
  codeGutterExtensions,
  gutterCompartment,
  inlineDiagnosticsCompartment,
  readOnlyCompartment,
  visualCompartment,
  wrapCompartment,
} from "./cmExtensions";
import {
  applyExternalDiagnostics,
  inlineDiagnosticsExtension,
} from "./diagnostics";
import { runEditorCommand, selectionFormatState } from "./formatCommands";
import { computeOutline, outlineActiveIndex } from "./outline";
import { computeStats } from "./stats";
import { visualLatexExtension } from "./visual";
import { preambleCollapsedField } from "./visual/atomicBlocks";
import { externalDocumentSync } from "./visual/effects";
import type {
  CodeEditorProps,
  DiagnosticClickInfo,
  EditorCommandId,
} from "./types";

/**
 * Hand-rolled CodeMirror 6 host. A pure shared primitive: controlled `value`,
 * line-anchored `diagnostics`, no knowledge of the domain. `language` is fixed
 * per instance — remount via `key` to switch files.
 */
export const CodeEditor = ({
  value,
  onChange,
  onSave,
  readOnly = false,
  wrapLines = false,
  visualMode = false,
  visualOptions,
  controllerRef,
  language = "latex",
  diagnostics,
  inlineDiagnostics = true,
  reveal,
  onDiagnosticClick,
  onStats,
  onFormatState,
  onOutline,
  onPasteTransformed,
  onOpenFile,
  resolveAssetUrl,
  onDropImage,
  onImageInsertSkipped,
  onEditTable,
  onEditBibliography,
  onModClick,
  className,
  ariaLabel,
}: CodeEditorProps) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  // `language` is fixed per mount (see docstring) — capture it for the
  // visual-mode effect, which must not enable itself on plain files.
  const languageRef = useRef(language);

  // Latest callbacks in refs — the view is created once but must always invoke
  // the current handlers.
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const onDiagnosticClickRef = useRef(onDiagnosticClick);
  const onStatsRef = useRef(onStats);
  const onFormatStateRef = useRef(onFormatState);
  const onOutlineRef = useRef(onOutline);
  const onPasteTransformedRef = useRef(onPasteTransformed);
  const onOpenFileRef = useRef(onOpenFile);
  const resolveAssetUrlRef = useRef(resolveAssetUrl);
  const onDropImageRef = useRef(onDropImage);
  const onImageInsertSkippedRef = useRef(onImageInsertSkipped);
  const onEditTableRef = useRef(onEditTable);
  const onEditBibliographyRef = useRef(onEditBibliography);
  const onModClickRef = useRef(onModClick);
  useEffect(() => {
    onChangeRef.current = onChange;
    onSaveRef.current = onSave;
    onDiagnosticClickRef.current = onDiagnosticClick;
    onStatsRef.current = onStats;
    onFormatStateRef.current = onFormatState;
    onOutlineRef.current = onOutline;
    onPasteTransformedRef.current = onPasteTransformed;
    onOpenFileRef.current = onOpenFile;
    resolveAssetUrlRef.current = resolveAssetUrl;
    onDropImageRef.current = onDropImage;
    onImageInsertSkippedRef.current = onImageInsertSkipped;
    onEditTableRef.current = onEditTable;
    onEditBibliographyRef.current = onEditBibliography;
    onModClickRef.current = onModClick;
  });
  // Whether to wire click handling is fixed at creation (stable per call site).
  const clickableRef = useRef(onDiagnosticClick != null);
  const statsEnabledRef = useRef(onStats != null);
  const formatStateEnabledRef = useRef(onFormatState != null);
  const outlineEnabledRef = useRef(onOutline != null);
  const modClickEnabledRef = useRef(onModClick != null);
  // Stable wrappers so compartment reconfigures always reach fresh handlers.
  // onOpenFile is present only when the host supplied it at creation (chips
  // fall back to reveal-only otherwise).
  const visualCallbacksRef = useRef({
    onPasteTransformed: () => onPasteTransformedRef.current?.(),
    ...(onOpenFile
      ? { onOpenFile: (path: string) => onOpenFileRef.current?.(path) }
      : {}),
    ...(resolveAssetUrl
      ? {
          resolveAssetUrl: (path: string) =>
            resolveAssetUrlRef.current?.(path) ?? null,
        }
      : {}),
    ...(onDropImage
      ? {
          onDropImage: (file: File) =>
            onDropImageRef.current?.(file) ?? Promise.resolve(null),
          onImageInsertSkipped: () => onImageInsertSkippedRef.current?.(),
        }
      : {}),
    ...(onEditTable
      ? {
          onEditTable: (source: string, commit: (next: string) => void): void =>
            onEditTableRef.current?.(source, commit),
        }
      : {}),
    ...(onEditBibliography
      ? {
          onEditBibliography: (
            source: string,
            commit: (next: string) => void,
          ): void => onEditBibliographyRef.current?.(source, commit),
        }
      : {}),
  });

  // Create the view exactly once. React 19 StrictMode mounts→unmounts→remounts
  // effects in dev; the ref guard + ref-based cleanup avoid two stacked views.
  useEffect(() => {
    const host = hostRef.current;
    if (!host || viewRef.current) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: value,
        extensions: buildExtensions({
          language,
          wrapLines,
          readOnly,
          visualMode,
          ...(visualOptions ? { visualOptions } : {}),
          visualCallbacks: visualCallbacksRef.current,
          inlineDiagnostics,
          onChange: (next) => onChangeRef.current?.(next),
          onSave: (next) => onSaveRef.current?.(next),
          ...(clickableRef.current
            ? {
                onInlineDiagnosticClick: (info: DiagnosticClickInfo) =>
                  onDiagnosticClickRef.current?.(info),
              }
            : {}),
          ...(statsEnabledRef.current
            ? { onStats: (s) => onStatsRef.current?.(s) }
            : {}),
          ...(formatStateEnabledRef.current
            ? { onFormatState: (s) => onFormatStateRef.current?.(s) }
            : {}),
          ...(outlineEnabledRef.current
            ? { onOutline: (o) => onOutlineRef.current?.(o) }
            : {}),
          ...(modClickEnabledRef.current
            ? { onModClick: (line: number) => onModClickRef.current?.(line) }
            : {}),
          ...(ariaLabel ? { ariaLabel } : {}),
        }),
      }),
      parent: host,
    });
    viewRef.current = view;
    if (controllerRef) {
      controllerRef.current = {
        exec: (id: EditorCommandId) => runEditorCommand(view, id),
        undo: () => undo(view),
        redo: () => redo(view),
        focus: () => {
          view.focus();
        },
      };
    }
    // Emit initial stats so the status bar isn't blank before the first edit.
    if (statsEnabledRef.current) onStatsRef.current?.(computeStats(view.state));
    // Seed the format toolbar only when the visual bundle is active (its
    // field is present) — code mode must stay free of full tree walks.
    if (view.state.field(preambleCollapsedField, false) !== undefined) {
      if (formatStateEnabledRef.current) {
        onFormatStateRef.current?.(selectionFormatState(view.state));
      }
      if (outlineEnabledRef.current) {
        const items = computeOutline(view.state);
        onOutlineRef.current?.({
          items,
          activeIndex: outlineActiveIndex(
            items,
            view.state.selection.main.head,
          ),
        });
      }
    }
    return () => {
      view.destroy();
      viewRef.current = null;
      if (controllerRef) controllerRef.current = null;
    };
    // Created once; later prop changes flow through the dedicated effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // External value → doc, guarding against echo from our own onChange.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (value !== current) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
        annotations: externalDocumentSync.of(true),
      });
    }
  }, [value]);

  useEffect(() => {
    const view = viewRef.current;
    if (view) applyExternalDiagnostics(view, diagnostics ?? []);
  }, [diagnostics]);

  useEffect(() => {
    const view = viewRef.current;
    if (view) {
      view.dispatch({
        effects: wrapCompartment.reconfigure(
          wrapLines ? EditorView.lineWrapping : [],
        ),
      });
    }
  }, [wrapLines]);

  useEffect(() => {
    const view = viewRef.current;
    if (view) {
      view.dispatch({
        effects: readOnlyCompartment.reconfigure(
          EditorState.readOnly.of(readOnly),
        ),
      });
    }
  }, [readOnly]);

  useEffect(() => {
    const view = viewRef.current;
    if (view) {
      view.dispatch({
        effects: inlineDiagnosticsCompartment.reconfigure(
          inlineDiagnostics ? inlineDiagnosticsExtension : [],
        ),
      });
    }
  }, [inlineDiagnostics]);

  // Visual mode (and its options) toggle via compartment reconfigure — an
  // effects-only transaction, so undo history, scroll and selection survive.
  useEffect(() => {
    const view = viewRef.current;
    if (view) {
      const active = visualMode && languageRef.current === "latex";
      view.dispatch({
        effects: [
          visualCompartment.reconfigure(
            active
              ? visualLatexExtension(visualOptions, visualCallbacksRef.current)
              : [],
          ),
          gutterCompartment.reconfigure(active ? [] : codeGutterExtensions()),
        ],
      });
    }
  }, [visualMode, visualOptions]);

  // Imperative scroll-to-line: select the line and center it. A new `reveal`
  // object identity (token) re-fires this even for the same line.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || !reveal) return;
    const lineNo = Math.min(Math.max(1, reveal.line), view.state.doc.lines);
    const line = view.state.doc.line(lineNo);
    view.dispatch({
      selection: { anchor: line.from, head: line.to },
      effects: EditorView.scrollIntoView(line.from, { y: "center" }),
    });
    view.focus();
  }, [reveal]);

  return (
    <div
      ref={hostRef}
      className={clsx("h-full min-h-0 w-full overflow-hidden", className)}
    />
  );
};
