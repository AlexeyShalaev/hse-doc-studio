import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import * as pdfjsLib from "pdfjs-dist";

export type PageDim = { num: number; widthPt: number; heightPt: number };

/**
 * A stamp painted directly onto a page (e.g. a signature), positioned in
 * millimetres from the page's top-left. Rendered clean — just the image, no
 * frame or handles — and non-interactive so text underneath stays selectable.
 *
 * When `invisible` is set the stamp marks an *invisible* crypto-signature field
 * (crypto_invisible mode): the real PDF carries no visible mark there, so the
 * preview draws a faint, clearly-labelled non-printing placeholder instead of
 * an image (`src` is ignored / may be null).
 */
export type PdfStamp = {
  page: number;
  src: string | null;
  xMm: number;
  yMm: number;
  widthMm: number;
  heightMm: number;
  label?: string;
  invisible?: boolean;
};

/** Page margins (mm) for the GOST text-area guide box. */
export type PageMargins = {
  topMm: number;
  rightMm: number;
  bottomMm: number;
  leftMm: number;
};

const HL_CLASS = "pdf-search-hl";

// 1 PDF point = 1/72 inch; 1 inch = 25.4 mm. `scale` is CSS px per point, so
// px-per-mm = scale * (points per mm).
const PT_PER_MM = 72 / 25.4;

type RawAnnot = {
  subtype?: string;
  rect?: number[];
  dest?: string | unknown[] | null;
  url?: string | null;
  unsafeUrl?: string | null;
};

type LinkRect = {
  id: string;
  left: number;
  top: number;
  width: number;
  height: number;
  targetPage: number | null;
  url: string | null;
};

const destToPage = async (
  pdf: pdfjsLib.PDFDocumentProxy,
  dest: string | unknown[] | null | undefined,
): Promise<number | null> => {
  if (dest == null) return null;
  try {
    const explicit =
      typeof dest === "string" ? await pdf.getDestination(dest) : dest;
    if (!Array.isArray(explicit) || explicit.length === 0) return null;
    const ref = explicit[0] as Parameters<typeof pdf.getPageIndex>[0] | null;
    if (ref == null || typeof ref !== "object") return null;
    return (await pdf.getPageIndex(ref)) + 1;
  } catch {
    return null;
  }
};

/**
 * Wrap every case-insensitive occurrence of `needle` in the text-layer spans
 * with a `<mark>` so a coloured box paints over the matched word on the canvas.
 * Restores originals on clear. Operates on the live DOM (built by pdf.js) so it
 * re-applies cleanly after re-renders. Cross-span matches aren't wrapped (rare).
 */
const highlightContainer = (
  container: HTMLElement | null,
  needle: string,
): void => {
  if (!container) return;
  const q = needle.trim().toLowerCase();
  const spans = container.querySelectorAll<HTMLElement>("span");
  for (const span of spans) {
    if (span.classList.contains("markedContent")) continue;
    const orig = span.dataset.orig ?? span.textContent ?? "";
    span.dataset.orig ??= orig;
    const lower = orig.toLowerCase();
    const hasMark = span.querySelector(`mark.${HL_CLASS}`) != null;
    if (!q || !lower.includes(q)) {
      if (hasMark) span.textContent = orig;
      continue;
    }
    const frag = document.createDocumentFragment();
    let from = 0;
    let idx = lower.indexOf(q, from);
    while (idx !== -1) {
      if (idx > from)
        frag.append(document.createTextNode(orig.slice(from, idx)));
      const mark = document.createElement("mark");
      mark.className = HL_CLASS;
      mark.textContent = orig.slice(idx, idx + q.length);
      frag.append(mark);
      from = idx + q.length;
      idx = lower.indexOf(q, from);
    }
    if (from < orig.length)
      frag.append(document.createTextNode(orig.slice(from)));
    span.replaceChildren(frag);
  }
};

type PdfPageProps = {
  pdf: pdfjsLib.PDFDocumentProxy;
  dim: PageDim;
  scale: number;
  /** Submitted search query — its occurrences are highlighted on the page. */
  searchQuery: string;
  /** Stamps belonging to this page, drawn clean over the rendered content. */
  stamps?: PdfStamp[] | undefined;
  /** Night/invert reading mode — inverts the rendered canvas only. */
  invert?: boolean;
  /** GOST text-area guide box (mm); null/undefined hides it. */
  marginGuideMm?: PageMargins | null | undefined;
  /** When true, dragging on the page measures a distance in mm. */
  measureMode?: boolean;
  /** Called when an internal PDF link (\ref/\cite/TOC) is followed. */
  onLinkClick?: ((pageNum: number) => void) | undefined;
  /** Ctrl/Cmd+click on the page → (page, x, y in PDF points from top-left). */
  onInverseClick?:
    | ((page: number, xPt: number, yPt: number) => void)
    | undefined;
  /** Transient highlight (SyncTeX forward jump), in PDF points from top-left. */
  flash?:
    | {
        xPt: number;
        yPt: number;
        widthPt: number;
        heightPt: number;
        token: number;
      }
    | null
    | undefined;
};

type MeasureState = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  active: boolean;
};

/**
 * One PDF page: a raster canvas plus a transparent, selectable text layer.
 * Renders lazily (only once scrolled near) but keeps itself rendered after,
 * re-rendering on zoom. The text layer makes text selectable/copyable and
 * findable via the browser's native Ctrl+F on rendered pages. On top of that it
 * carries optional clean overlays: signature stamps, clickable links, a GOST
 * margin guide, and a drag-to-measure ruler.
 */
export const PdfPage = ({
  pdf,
  dim,
  scale,
  searchQuery,
  stamps,
  invert,
  marginGuideMm,
  measureMode,
  onLinkClick,
  onInverseClick,
  flash,
}: PdfPageProps) => {
  const { t } = useTranslation("pdfViewer");
  const pxPerMm = scale * PT_PER_MM;

  const handleClick = (e: React.MouseEvent<HTMLDivElement>): void => {
    if (!onInverseClick || !(e.ctrlKey || e.metaKey)) return;
    const rect = e.currentTarget.getBoundingClientRect();
    onInverseClick(
      dim.num,
      (e.clientX - rect.left) / scale,
      (e.clientY - rect.top) / scale,
    );
  };
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [links, setLinks] = useState<LinkRect[]>([]);
  // Latest query read inside the render effect without making it a dependency
  // (so changing the query re-highlights via the effect below, not re-render).
  const searchRef = useRef(searchQuery);
  useEffect(() => {
    searchRef.current = searchQuery;
  });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          io.disconnect();
        }
      },
      { rootMargin: "1200px" },
    );
    io.observe(el);
    return () => {
      io.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!visible) return;
    const ctl: {
      cancelled: boolean;
      render: pdfjsLib.RenderTask | undefined;
      text: pdfjsLib.TextLayer | undefined;
    } = { cancelled: false, render: undefined, text: undefined };

    void (async () => {
      const page = await pdf.getPage(dim.num);
      if (ctl.cancelled) return;
      const dpr = window.devicePixelRatio || 1;
      const cssViewport = page.getViewport({ scale });
      const rasterViewport = page.getViewport({ scale: scale * dpr });

      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      if (canvas && ctx) {
        canvas.width = rasterViewport.width;
        canvas.height = rasterViewport.height;
        ctl.render = page.render({
          canvasContext: ctx,
          viewport: rasterViewport,
          canvas,
        });
        await ctl.render.promise.catch(() => undefined);
        // ctl.cancelled is flipped in cleanup; CFA can't see that cross-closure.
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        if (ctl.cancelled) return;
      }

      const textContainer = textRef.current;
      if (textContainer) {
        textContainer.replaceChildren();
        // pdf.js v6 drives span font-size from `--total-scale-factor` (the
        // display scale); `--scale-factor` is the older name kept for safety.
        textContainer.style.setProperty("--total-scale-factor", String(scale));
        textContainer.style.setProperty("--scale-factor", String(scale));
        ctl.text = new pdfjsLib.TextLayer({
          textContentSource: page.streamTextContent(),
          container: textContainer,
          viewport: cssViewport,
        });
        await ctl.text.render().catch(() => undefined);
        highlightContainer(textContainer, searchRef.current);
      }

      // Clickable links (\ref/\cite/TOC jumps + external URLs from hyperref).
      const annots = (await page
        .getAnnotations()
        .catch(() => [])) as RawAnnot[];
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (ctl.cancelled) return;
      const rects: LinkRect[] = [];
      for (const [i, a] of annots.entries()) {
        if (a.subtype !== "Link" || !a.rect) continue;
        const url = a.url ?? a.unsafeUrl ?? null;
        const targetPage = url ? null : await destToPage(pdf, a.dest);
        if (!url && targetPage == null) continue;
        const r = cssViewport.convertToViewportRectangle(a.rect) as number[];
        const [rx1, ry1, rx2, ry2] = r;
        if (rx1 == null || ry1 == null || rx2 == null || ry2 == null) continue;
        rects.push({
          id: `${String(dim.num)}-${String(i)}`,
          left: Math.min(rx1, rx2),
          top: Math.min(ry1, ry2),
          width: Math.abs(rx2 - rx1),
          height: Math.abs(ry2 - ry1),
          targetPage,
          url,
        });
      }
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (!ctl.cancelled) setLinks(rects);
    })().catch(() => undefined);

    return () => {
      ctl.cancelled = true;
      ctl.render?.cancel();
      ctl.text?.cancel();
    };
  }, [visible, scale, pdf, dim.num]);

  // Re-apply highlights when the query changes (without re-rendering the page).
  useEffect(() => {
    highlightContainer(textRef.current, searchQuery);
  }, [searchQuery]);

  return (
    <div
      ref={wrapRef}
      data-page={dim.num}
      onClick={handleClick}
      style={{
        position: "relative",
        width: dim.widthPt * scale,
        height: dim.heightPt * scale,
        background: "#fff",
        boxShadow: "0 2px 12px rgba(0,0,0,0.4)",
        flexShrink: 0,
      }}
    >
      <canvas
        ref={canvasRef}
        className={invert ? "pdf-page-canvas pdf-invert" : "pdf-page-canvas"}
      />
      <div ref={textRef} className="textLayer" />

      {flash && (
        <div
          key={flash.token}
          className="pdf-sync-flash"
          style={{
            left: flash.xPt * scale,
            top: flash.yPt * scale,
            width: Math.max(flash.widthPt * scale, 8),
            height: Math.max(flash.heightPt * scale, 12),
          }}
        />
      )}

      {marginGuideMm && (
        <div
          className="pdf-margin-guide"
          style={{
            left: marginGuideMm.leftMm * pxPerMm,
            top: marginGuideMm.topMm * pxPerMm,
            right: marginGuideMm.rightMm * pxPerMm,
            bottom: marginGuideMm.bottomMm * pxPerMm,
          }}
        />
      )}

      {links.length > 0 && (
        <div className="pdf-link-layer">
          {links.map((l) =>
            l.url ? (
              <a
                key={l.id}
                href={l.url}
                target="_blank"
                rel="noreferrer"
                className="pdf-link"
                title={l.url}
                style={{
                  left: l.left,
                  top: l.top,
                  width: l.width,
                  height: l.height,
                }}
              />
            ) : (
              <button
                key={l.id}
                type="button"
                className="pdf-link"
                title={t("page.linkTitle", { page: l.targetPage })}
                onClick={() => {
                  if (l.targetPage != null) onLinkClick?.(l.targetPage);
                }}
                style={{
                  left: l.left,
                  top: l.top,
                  width: l.width,
                  height: l.height,
                }}
              />
            ),
          )}
        </div>
      )}

      {stamps && stamps.length > 0 && (
        <div className="pdf-stamp-layer">
          {stamps.map((s, i) => {
            const box = {
              position: "absolute" as const,
              left: s.xMm * pxPerMm,
              top: s.yMm * pxPerMm,
              width: s.widthMm * pxPerMm,
              height: s.heightMm * pxPerMm,
            };
            // Invisible crypto field: faint, dashed, non-printing placeholder
            // so the user can locate it even though the real PDF shows nothing.
            if (s.invisible || !s.src) {
              return (
                <div
                  key={`inv#${String(i)}`}
                  className="pdf-stamp-invisible"
                  style={box}
                  title={t("page.invisibleSignatureTitle", {
                    label: s.label ?? t("page.signatureFallbackLabel"),
                  })}
                >
                  <span>{t("page.invisibleSignature")}</span>
                </div>
              );
            }
            return (
              <img
                key={`${s.src}#${String(i)}`}
                src={s.src}
                alt={s.label ?? ""}
                draggable={false}
                style={{ ...box, objectFit: "contain" }}
              />
            );
          })}
        </div>
      )}

      {measureMode && <MeasureOverlay pxPerMm={pxPerMm} />}
    </div>
  );
};

/**
 * Drag-to-measure ruler. Lives in its own component so it mounts only while the
 * tool is active — unmounting clears the in-progress line with no extra effect.
 * Exported so the visual-diff view can offer the same ruler over its stage.
 */
export const MeasureOverlay = ({ pxPerMm }: { pxPerMm: number }) => {
  const { t } = useTranslation("pdfViewer");
  const [measure, setMeasure] = useState<MeasureState | null>(null);

  const onDown = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (e.button !== 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    e.currentTarget.setPointerCapture(e.pointerId);
    setMeasure({ x1: x, y1: y, x2: x, y2: y, active: true });
  };
  const onMove = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (!measure?.active) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setMeasure({
      ...measure,
      x2: e.clientX - rect.left,
      y2: e.clientY - rect.top,
    });
  };
  const onUp = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (!measure?.active) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    setMeasure({ ...measure, active: false });
  };

  const distMm = measure
    ? Math.hypot(measure.x2 - measure.x1, measure.y2 - measure.y1) / pxPerMm
    : 0;

  return (
    <div
      className="pdf-measure-layer"
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
    >
      {measure && (
        <>
          <svg className="pdf-measure-svg">
            <line
              x1={measure.x1}
              y1={measure.y1}
              x2={measure.x2}
              y2={measure.y2}
            />
          </svg>
          <div
            className="pdf-measure-label"
            style={{
              left: (measure.x1 + measure.x2) / 2,
              top: (measure.y1 + measure.y2) / 2,
            }}
          >
            {t("measure.mm", { value: distMm.toFixed(1) })}
          </div>
        </>
      )}
    </div>
  );
};
