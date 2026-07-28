import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Archive,
  Download,
  ExternalLink,
  File as FileIcon,
  FileEdit,
  FileText,
  GitCompare,
  Globe,
  PenTool,
  Presentation,
  RefreshCw,
} from "lucide-react";
import type { z } from "zod";
import { useAppSettings } from "@entities/app-settings";
import {
  documentKeys,
  getDocMeta,
  isOfficeEditablePath,
  useCompiles,
} from "@entities/document";
import type { DocumentResponseSchema } from "@entities/document";
import type { ProjectResponseSchema } from "@entities/project";
import { useSignaturesState } from "@entities/signature";
import { synctexApi } from "@entities/synctex";
import { env } from "@shared/config";
import {
  toast,
  useSyncTexStore,
  useWorkspaceStore,
  localeTag,
} from "@shared/lib";
import {
  PdfDiffView,
  PdfViewer,
  type DiffBaseOption,
  type PdfStamp,
} from "@shared/ui";

// Fallback signature aspect (height / width) when the PNG's natural size is
// unknown — matches the signature stamper's default.
const DEFAULT_SIG_ASPECT = 0.4;

// GOST 7.32-2017 page margins (mm): left 30, right 10, top 20, bottom 20.
const GOST_MARGINS = { leftMm: 30, rightMm: 10, topMm: 20, bottomMm: 20 };

type Document = z.infer<typeof DocumentResponseSchema>;
type Project = z.infer<typeof ProjectResponseSchema>;

export type PreviewPaneProps = {
  project: Project;
  doc: Document;
};

const fileUrl = (projectId: string, relPath: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${relPath}`;

const signedPdfDownloadUrl = (projectId: string, docId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/docs/${docId}/pdf/signed`;

const archivedPdfUrl = (
  projectId: string,
  docId: string,
  compileId: string,
): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/documents/${docId}/compiles/${compileId}/pdf`;

export const PreviewPane = ({ project, doc }: PreviewPaneProps) => {
  const { t } = useTranslation("documents");
  // Pass the doc so paths/name come from the API (team-aware).
  const meta = getDocMeta(doc.id, doc, project.lang ?? "ru");
  const { data: settings } = useAppSettings();
  const { data: signaturesState } = useSignaturesState(project.id);
  const pdfJump = useSyncTexStore((s) => s.pdfJump);
  const requestSourceJump = useSyncTexStore((s) => s.requestSourceJump);
  const requestSourceFind = useSyncTexStore((s) => s.requestSourceFind);
  const askAgent = useWorkspaceStore((s) => s.askAgent);

  // Office-editable artifact (pptx variant, or any custom word/cell/slide
  // upload): saving from the office editor reconverts the PDF preview
  // server-side (no compile, so nothing else invalidates the doc detail).
  // While this pane is open, quietly re-read the detail so the fresh
  // preview_updated_at (or a first-ever preview) is picked up within seconds.
  const queryClient = useQueryClient();
  const isOfficeEditableArtifactPreview = isOfficeEditablePath(
    doc.output_file ?? "",
  );
  useEffect(() => {
    if (!isOfficeEditableArtifactPreview) return;
    const id = window.setInterval(() => {
      void queryClient.invalidateQueries({
        queryKey: documentKeys.detail(project.id, doc.id),
      });
    }, 4000);
    return () => {
      window.clearInterval(id);
    };
  }, [isOfficeEditableArtifactPreview, queryClient, project.id, doc.id]);
  const [, setSearchParams] = useSearchParams();
  const openInSourceTab = () => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("tab", "source");
        return next;
      },
      { replace: true },
    );
  };

  // Selected PDF text → agent / source search (the floating bar in PdfViewer).
  const onAskAgent = (text: string): void => {
    askAgent(t("preview.askAgentPrompt", { name: meta.name, text }));
  };
  const onFindInSource = (text: string): void => {
    requestSourceFind(text);
  };

  // Ctrl/Cmd+click in the PDF → ask the backend which source line is there, then
  // hand it to the source editor (DocumentTabs switches to the source tab).
  const onInverseSync = (page: number, xPt: number, yPt: number): void => {
    void synctexApi
      .inverse(project.id, doc.id, page, xPt, yPt)
      .then((r) => {
        requestSourceJump({ file: r.file, line: r.line, column: r.column });
      })
      .catch(() => {
        toast.warning(t("preview.syncTexUnavailable"));
      });
  };
  // Document-level prose count (words/chars as rendered, excluding LaTeX
  // commands/comments/TOC, includes followed) — computed by texcount on the
  // last successful build and carried on the compile record.
  const { data: compiles } = useCompiles(project.id, doc.id);
  const lastCompile = useMemo(
    () => compiles?.find((c) => c.id === doc.last_compile_id) ?? compiles?.[0],
    [compiles, doc.last_compile_id],
  );

  // Visual diff against an earlier build. Bases = successful prior builds
  // (newest first), each with an archived PDF. The preview always shows the
  // newest successful build (a failed compile doesn't overwrite the on-disk
  // PDF), so that build *is* the current version — never offer it as a base to
  // compare against itself. We can't key off doc.last_compile_id here: when the
  // last compile failed (or it's null) it points at something other than the
  // shown build, leaking the current version back into the list.
  const [diffOpen, setDiffOpen] = useState(false);
  // Manual reload counter for the live HTML (reveal) preview iframe — the
  // artifact IS the source file, so edits show up without a rebuild.
  const [htmlRefresh, setHtmlRefresh] = useState(0);
  const diffBases = useMemo<DiffBaseOption[]>(() => {
    if (!compiles) return [];
    const successes = compiles.filter((c) => c.status === "success");
    const currentId = successes.at(-1)?.id;
    return successes
      .filter((c) => c.id !== currentId)
      .reverse()
      .map((c) => {
        const dateLabel = new Date(c.started_at).toLocaleString(localeTag(), {
          day: "2-digit",
          month: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        });
        return {
          id: c.id,
          label:
            c.pages != null
              ? t("preview.diffBasePages", { label: dateLabel, count: c.pages })
              : dateLabel,
        };
      });
  }, [compiles, t]);
  // Stable identity so the diff view's base-load effect (deps: [baseId,
  // baseUrlFor]) doesn't reload the archived PDF on every unrelated PreviewPane
  // re-render (SyncTeX jumps, recompiles, signature updates).
  const baseUrlFor = useCallback(
    (compileId: string) => archivedPdfUrl(project.id, doc.id, compileId),
    [project.id, doc.id],
  );
  const hasBuild =
    doc.status === "ok" || doc.status === "warn" || doc.status === "locked";
  // Prefer the API-declared output path (authoritative in team layouts); the
  // .tex→.pdf derivation stays as the legacy fallback. The artifact is not
  // necessarily a PDF: copy-only presentation variants publish .pptx / .html.
  const artifactRelPath =
    doc.output_file ?? meta.file.replace(/\.tex$/, ".pdf");
  const artifactHref = fileUrl(project.id, artifactRelPath);
  const isPdfArtifact = /\.pdf$/i.test(artifactRelPath);
  const signedHref = signedPdfDownloadUrl(project.id, doc.id);
  // Only surface the "signed PDF" button when at least one slot is wired up
  // and enabled on *this* doc. Otherwise the signed download would be byte-
  // identical to the regular one and the button would be pure noise.
  const docPlacements = signaturesState?.placements[doc.id] ?? {};
  const hasEnabledSignature = Object.entries(docPlacements).some(
    ([slotId, p]) => p.enabled && signaturesState?.slots[slotId]?.png_path,
  );
  // Detached mode: at least one enabled slot uses CAdES → download is a zip.
  const hasDetachedSlot = Object.entries(docPlacements).some(
    ([slotId, p]) =>
      p.enabled &&
      signaturesState?.slots[slotId]?.png_path &&
      signaturesState?.slots[slotId]?.sign_mode === "detached",
  );

  // Paint the signatures straight onto the preview pages — same placement the
  // signed PDF would use — so the user sees exactly where each signature lands
  // without downloading the stamped file. Visible modes (image / image_crypto /
  // detached) draw the PNG; crypto_invisible draws a faint non-printing marker
  // so the field's location is still visible while editing.
  const stamps = useMemo<PdfStamp[]>(() => {
    if (!signaturesState) return [];
    const out: PdfStamp[] = [];
    for (const [slotId, p] of Object.entries(
      signaturesState.placements[doc.id] ?? {},
    )) {
      const slot = signaturesState.slots[slotId];
      if (!p.enabled || !slot?.png_path) continue;
      const nw = slot.natural_width_px;
      const nh = slot.natural_height_px;
      const aspect = nw && nh && nw > 0 ? nh / nw : DEFAULT_SIG_ASPECT;
      const isInvisible = slot.sign_mode === "crypto_invisible";
      out.push({
        page: p.page,
        src: isInvisible ? null : fileUrl(project.id, slot.png_path),
        xMm: p.x_mm,
        yMm: p.y_mm,
        widthMm: p.width_mm,
        heightMm: p.width_mm * aspect,
        label: slotId,
        invisible: isInvisible,
      });
    }
    return out;
  }, [signaturesState, doc.id, project.id]);

  if (!hasBuild) {
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{ flex: 1, padding: 40, gap: 16, minHeight: 0 }}
      >
        <div
          className="stripes flex items-center justify-center"
          style={{
            width: 220,
            height: 280,
            borderRadius: 6,
            border: "1px solid var(--border-strong)",
            color: "var(--fg-3)",
          }}
        >
          <div className="flex flex-col items-center" style={{ gap: 6 }}>
            <FileText size={28} />
            <span
              className="mono"
              style={{ fontSize: 10, textTransform: "uppercase" }}
            >
              {t("preview.notBuilt")}
            </span>
          </div>
        </div>
        <p
          className="dim"
          style={{
            margin: 0,
            textAlign: "center",
            maxWidth: 380,
            fontSize: 12.5,
          }}
        >
          {doc.engine === null ? (
            // Copy-only variant (pptx/reveal): no latexmk involved — the build
            // just runs the checks and publishes the file.
            t("preview.notBuiltCopyHint")
          ) : (
            <>
              {t("preview.notBuiltHint")}
              {settings
                ? t("preview.notBuiltEngineHint", {
                    engine: settings.default_engine,
                    passes: settings.latex_passes,
                    passWord: t("preview.passWord", {
                      count: settings.latex_passes,
                    }),
                  })
                : "."}
            </>
          )}
        </p>
      </div>
    );
  }

  // Non-PDF artifact (pptx/reveal presentation variants): pdf.js can't render
  // it, so offer download / open-in-tab instead. Words counter, GOST guides,
  // signatures and the visual diff are PDF-only — they simply don't render
  // here.
  if (!isPdfArtifact) {
    const artifactName = artifactRelPath.split("/").pop() ?? artifactRelPath;
    const dotIdx = artifactName.lastIndexOf(".");
    const ext = dotIdx >= 0 ? artifactName.slice(dotIdx + 1).toLowerCase() : "";
    const isHtml = ext === "html" || ext === "htm";

    // HTML artifact (reveal presentation): the browser renders it natively —
    // embed a live iframe (slides are interactive right in the pane). NB: the
    // stock reveal template loads reveal.js from a CDN, so offline it shows
    // unstyled; the deliverable stays the .html itself.
    if (isHtml) {
      const htmlSrc = `${artifactHref}${htmlRefresh > 0 ? `?r=${htmlRefresh}` : ""}`;
      return (
        <div className="flex flex-col" style={{ flex: 1, minHeight: 0 }}>
          <div
            className="flex items-center gap-2"
            style={{
              padding: "6px 10px",
              borderBottom: "1px solid var(--border)",
              flexShrink: 0,
            }}
          >
            <Globe
              size={13}
              style={{ color: "var(--accent)", flexShrink: 0 }}
            />
            <span
              className="mono dim tt shrink-0"
              data-tt={t("preview.htmlPreviewTooltip")}
              style={{ whiteSpace: "nowrap", fontSize: 11 }}
            >
              {t("preview.htmlPreviewBadge")}
            </span>
            <span
              className="mono dim truncate"
              style={{ fontSize: 11, flex: 1, minWidth: 0, textAlign: "right" }}
            >
              {artifactName}
            </span>
            <button
              type="button"
              className="btn shrink-0"
              onClick={() => {
                setHtmlRefresh((n) => n + 1);
              }}
            >
              <RefreshCw size={12} />
              {t("preview.refresh")}
            </button>
            <button
              type="button"
              className="btn shrink-0"
              onClick={() => {
                window.open(artifactHref, "_blank", "noopener");
              }}
            >
              <ExternalLink size={12} />
              {t("preview.openInNewTab")}
            </button>
            <a
              href={artifactHref}
              className="btn shrink-0"
              download={artifactName}
            >
              <Download size={12} />
              {t("preview.download")}
            </a>
          </div>
          <iframe
            key={`${doc.last_compile_id ?? ""}:${htmlRefresh}`}
            src={htmlSrc}
            title={`${meta.code} HTML preview`}
            // Scripts must run (reveal.js); top-navigation stays sandboxed.
            sandbox="allow-scripts allow-same-origin allow-popups"
            style={{
              flex: 1,
              minHeight: 0,
              border: "none",
              background: "#fff",
              width: "100%",
            }}
          />
        </div>
      );
    }

    // A converted PDF preview (pptx → Gotenberg/LibreOffice on build or after
    // an office-editor save) renders in the normal viewer; the deliverable
    // stays the original file, so the toolbar carries a "converted" badge + a
    // download button for it. No stamps/GOST guides/SyncTeX — those are
    // LaTeX-document concerns. The mtime-based refreshKey (PdfViewer bakes it
    // into the URL) reloads the PDF after saves, which never touch
    // last_compile_id.
    if (doc.preview_file) {
      return (
        <PdfViewer
          url={fileUrl(project.id, doc.preview_file)}
          refreshKey={
            doc.preview_updated_at ?? doc.last_compile_id ?? doc.preview_file
          }
          ariaLabel={`${meta.code} preview`}
          storageKey={`${project.id}:${doc.id}`}
          toolbarExtras={
            <>
              {doc.custom_file != null && (
                <span
                  className="chip"
                  style={{
                    background: "var(--bg-3)",
                    color: "var(--fg-1)",
                    fontSize: 10.5,
                  }}
                >
                  {t("preview.customFileBadge")}
                </span>
              )}
              <span
                className="mono dim tt shrink-0"
                data-tt={t("preview.convertedTooltip", { ext: `.${ext}` })}
                style={{ whiteSpace: "nowrap" }}
              >
                {t("preview.convertedBadge")}
              </span>
              <a
                href={artifactHref}
                className="btn shrink-0"
                download={artifactName}
              >
                <Download size={12} />
                {t("preview.downloadOriginal", { ext: `.${ext}` })}
              </a>
            </>
          }
        />
      );
    }
    const isOfficeEditableExt = isOfficeEditablePath(artifactRelPath);
    const isSlideExt = ext === "pptx" || ext === "ppt" || ext === "odp";
    const ArtifactIcon = isHtml
      ? Globe
      : isSlideExt
        ? Presentation
        : isOfficeEditableExt
          ? FileEdit
          : FileIcon;
    // A custom file in a format we don't recognize at all (not PDF, not an
    // office format ONLYOFFICE/Gotenberg can handle) — offer the same
    // VS-Code-like fallback as the Source tab: open it as plain text instead
    // of only a download card.
    const offerTextFallback = doc.custom_file != null && !isOfficeEditableExt;
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{ flex: 1, padding: 40, gap: 16, minHeight: 0 }}
      >
        <div
          className="stripes flex items-center justify-center"
          style={{
            width: 220,
            height: 280,
            borderRadius: 6,
            border: "1px solid var(--border-strong)",
            color: "var(--fg-3)",
          }}
        >
          <div className="flex flex-col items-center" style={{ gap: 6 }}>
            <ArtifactIcon size={28} />
            {ext && (
              <span
                className="mono"
                style={{ fontSize: 10, textTransform: "uppercase" }}
              >
                .{ext}
              </span>
            )}
          </div>
        </div>
        <span className="mono" style={{ fontSize: 12.5 }}>
          {artifactName}
        </span>
        <p
          className="dim"
          style={{
            margin: 0,
            textAlign: "center",
            maxWidth: 380,
            fontSize: 12.5,
          }}
        >
          {doc.custom_file != null
            ? t("preview.customNoPreviewHint")
            : t("preview.nonPdfHint")}
        </p>
        {isOfficeEditableExt && (
          // A converted PDF preview needs the Gotenberg office service — point
          // at the settings section where it can be installed in one click.
          // Same root cause (converter not installed) for both the template
          // pptx variant and a custom docx/xlsx/pptx upload.
          <Link
            to="/settings/presentations"
            className="dim"
            style={{
              fontSize: 11.5,
              textAlign: "center",
              maxWidth: 380,
              textDecoration: "underline",
              textUnderlineOffset: 3,
            }}
          >
            {t("preview.officeConvertHint")}
          </Link>
        )}
        <div className="flex items-center gap-2">
          <a href={artifactHref} className="btn" download={artifactName}>
            <Download size={12} />
            {t("preview.download")}
          </a>
          {offerTextFallback && (
            <button type="button" className="btn" onClick={openInSourceTab}>
              <FileEdit size={12} />
              {t("preview.openAsText")}
            </button>
          )}
          {isHtml && (
            <button
              type="button"
              className="btn"
              onClick={() => {
                window.open(artifactHref, "_blank", "noopener");
              }}
            >
              <ExternalLink size={12} />
              {t("preview.openInNewTab")}
            </button>
          )}
        </div>
      </div>
    );
  }

  if (diffOpen) {
    return (
      <PdfDiffView
        currentUrl={artifactHref}
        baseUrlFor={baseUrlFor}
        bases={diffBases}
        marginGuideMm={GOST_MARGINS}
        onClose={() => {
          setDiffOpen(false);
        }}
      />
    );
  }

  return (
    <PdfViewer
      url={artifactHref}
      refreshKey={doc.last_compile_id ?? artifactRelPath}
      ariaLabel={`${meta.code} preview`}
      stamps={stamps}
      marginGuideMm={GOST_MARGINS}
      storageKey={`${project.id}:${doc.id}`}
      onInverseSync={onInverseSync}
      jump={pdfJump}
      onAskAgent={onAskAgent}
      onFindInSource={onFindInSource}
      toolbarExtras={
        <>
          <span className="mono dim truncate" style={{ maxWidth: 200 }}>
            {meta.out}
          </span>
          {lastCompile?.words != null && (
            <span
              className="mono dim tt shrink-0"
              data-tt={t("preview.wordCountTooltip")}
              style={{ whiteSpace: "nowrap" }}
            >
              {lastCompile.chars != null
                ? t("preview.wordsChars", {
                    count: lastCompile.words,
                    chars: lastCompile.chars.toLocaleString(localeTag()),
                  })
                : t("preview.words", { count: lastCompile.words })}
            </span>
          )}
          {diffBases.length > 0 && (
            <button
              type="button"
              className="btn xs shrink-0"
              title={t("preview.compareWithPrevious")}
              onClick={() => {
                setDiffOpen(true);
              }}
            >
              <GitCompare size={11} />
              {t("preview.compare")}
            </button>
          )}
          <a
            href={artifactHref}
            className="btn xs shrink-0"
            download={meta.out}
            target="_blank"
            rel="noreferrer"
          >
            <Download size={11} />
            PDF
          </a>
          {hasEnabledSignature && (
            <a
              href={signedHref}
              className="btn xs shrink-0"
              download
              title={
                hasDetachedSlot
                  ? t("preview.downloadArchiveTitle")
                  : t("preview.downloadSignedTitle")
              }
            >
              {hasDetachedSlot ? <Archive size={11} /> : <PenTool size={11} />}
              {hasDetachedSlot
                ? t("preview.pdfWithSig")
                : t("preview.withSignatures")}
            </a>
          )}
        </>
      }
    />
  );
};
