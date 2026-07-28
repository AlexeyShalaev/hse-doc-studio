import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronLeft,
  ChevronRight,
  Columns2,
  Contrast,
  Frame,
  Images,
  Layers,
  List,
  Minus,
  Moon,
  Plus,
  Printer,
  Ruler,
  Scan,
  Search,
  X,
} from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { Spinner } from "../Spinner";
import { MeasureOverlay, type PageDim, type PageMargins } from "./PdfPage";
import { PdfThumbnails } from "./PdfThumbnails";
import { PdfOutline, type OutlineEntry } from "./PdfOutline";
import { countOccurrences, getOutlineFor, loadPageDims } from "./pdfDoc";
import "./pdfViewer.css";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const PT_TO_PX = 96 / 72;
// 1 PDF point = 1/72 inch; 1 inch = 25.4 mm. `scale` is CSS px per point.
const PT_PER_MM = 72 / 25.4;
const DEFAULT_SCALE = PT_TO_PX * 0.9;
const MIN_SCALE = 0.2;
const MAX_SCALE = 5;
const FIT_PADDING = 24;
// A4 width in points — fallback for the fit math before page dims have loaded.
const A4_WIDTH_PT = 595.28;

export type DiffBaseOption = { id: string; label: string };

export type PdfDiffViewProps = {
  /** URL of the current (new) PDF. */
  currentUrl: string;
  /** Builds the URL of a base (old) PDF for a given compile id. */
  baseUrlFor: (compileId: string) => string;
  /** Prior builds available as a diff base (most recent first). */
  bases: DiffBaseOption[];
  /** When set, the GOST margin guide can be toggled on (drawn on the page). */
  marginGuideMm?: PageMargins;
  onClose: () => void;
};

type Mode = "swipe" | "fade" | "diff";

const lum = (d: Uint8ClampedArray, i: number): number =>
  0.299 * (d[i] ?? 0) + 0.587 * (d[i + 1] ?? 0) + 0.114 * (d[i + 2] ?? 0);

// Build a per-pixel diff: unchanged ink → grey, added (new) → green, removed
// (old) → red, blank → white. Returns false if the canvases don't line up.
const computeDiff = (
  base: HTMLCanvasElement,
  cur: HTMLCanvasElement,
  out: HTMLCanvasElement,
): boolean => {
  if (base.width !== cur.width || base.height !== cur.height) return false;
  const w = cur.width;
  const h = cur.height;
  const bctx = base.getContext("2d");
  const cctx = cur.getContext("2d");
  const octx = out.getContext("2d");
  if (!bctx || !cctx || !octx) return false;
  out.width = w;
  out.height = h;
  const bd = bctx.getImageData(0, 0, w, h).data;
  const cd = cctx.getImageData(0, 0, w, h).data;
  const od = octx.createImageData(w, h);
  const o = od.data;
  const INK = 185;
  for (let i = 0; i < o.length; i += 4) {
    const ib = lum(bd, i) < INK;
    const ic = lum(cd, i) < INK;
    let r = 255;
    let g = 255;
    let b = 255;
    if (ib && ic) {
      r = 206;
      g = 206;
      b = 206;
    } else if (ic && !ib) {
      r = 38;
      g = 166;
      b = 74;
    } else if (ib && !ic) {
      r = 208;
      g = 52;
      b = 52;
    }
    o[i] = r;
    o[i + 1] = g;
    o[i + 2] = b;
    o[i + 3] = 255;
  }
  octx.putImageData(od, 0, 0);
  return true;
};

// Size `canvas` for the page and kick off the render, returning the live
// RenderTask so the caller can cancel it (pdf.js v6 forbids two concurrent
// renders on the same canvas). `isCancelled` is checked after the async
// getPage so a superseded run never starts a render on a shared canvas.
const renderPage = async (
  doc: pdfjsLib.PDFDocumentProxy,
  pageNum: number,
  scale: number,
  canvas: HTMLCanvasElement,
  isCancelled: () => boolean,
): Promise<pdfjsLib.RenderTask | null> => {
  const page = await doc.getPage(pageNum);
  if (isCancelled()) return null;
  const dpr = window.devicePixelRatio || 1;
  const vp = page.getViewport({ scale });
  const rvp = page.getViewport({ scale: scale * dpr });
  canvas.width = rvp.width;
  canvas.height = rvp.height;
  canvas.style.width = `${String(vp.width)}px`;
  canvas.style.height = `${String(vp.height)}px`;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  return page.render({ canvasContext: ctx, viewport: rvp, canvas });
};

// Paint `dst` solid white at `src`'s exact raster + CSS size. Used when the base
// build has no page for the current page (it's older/shorter, or still loading):
// a white base makes the page read as "entirely added" in every mode and keeps
// the pixel-diff aligned, instead of a cleared (transparent → read as ink → all
// red) canvas or a stale-size false "page changed" warning.
const paintBlank = (src: HTMLCanvasElement, dst: HTMLCanvasElement): void => {
  dst.width = src.width;
  dst.height = src.height;
  dst.style.width = src.style.width;
  dst.style.height = src.style.height;
  const ctx = dst.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, dst.width, dst.height);
};

export const PdfDiffView = ({
  currentUrl,
  baseUrlFor,
  bases,
  marginGuideMm,
  onClose,
}: PdfDiffViewProps) => {
  const { t } = useTranslation("pdfViewer");
  const areaRef = useRef<HTMLDivElement>(null);
  const baseCanvasRef = useRef<HTMLCanvasElement>(null);
  const curCanvasRef = useRef<HTMLCanvasElement>(null);
  const diffCanvasRef = useRef<HTMLCanvasElement>(null);
  const pageFocusedRef = useRef(false);
  const zoomFocusedRef = useRef(false);
  const textCacheRef = useRef<Map<number, string>>(new Map());

  const [baseId, setBaseId] = useState(() => bases[0]?.id ?? "");
  const [curDoc, setCurDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [baseDoc, setBaseDoc] = useState<pdfjsLib.PDFDocumentProxy | null>(
    null,
  );
  const [pages, setPages] = useState<PageDim[]>([]);
  const [outline, setOutline] = useState<OutlineEntry[]>([]);
  const [baseError, setBaseError] = useState(false);
  const [page, setPage] = useState(1);
  const [pageDraft, setPageDraft] = useState("1");
  const [mode, setMode] = useState<Mode>("diff");
  const [swipe, setSwipe] = useState(50);
  const [fade, setFade] = useState(0.5);
  const [availWidth, setAvailWidth] = useState(0);
  const [disp, setDisp] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [diffAligned, setDiffAligned] = useState(true);

  const [fit, setFit] = useState(true);
  const [manualScale, setManualScale] = useState(DEFAULT_SCALE);
  const [zoomDraft, setZoomDraft] = useState(() =>
    String(Math.round((DEFAULT_SCALE / PT_TO_PX) * 100)),
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<"outline" | "thumbs">("thumbs");
  const [invert, setInvert] = useState(false);
  const [guidesOn, setGuidesOn] = useState(false);
  const [measureMode, setMeasureMode] = useState(false);

  const [query, setQuery] = useState("");
  const [matchPages, setMatchPages] = useState<number[]>([]);
  const [matchIdx, setMatchIdx] = useState(0);

  const numPages = pages.length > 0 ? pages.length : (curDoc?.numPages ?? 0);
  const curWidthPt = pages[page - 1]?.widthPt ?? A4_WIDTH_PT;
  const fitScale = useMemo(() => {
    if (availWidth === 0) return DEFAULT_SCALE;
    return Math.min(
      MAX_SCALE,
      Math.max(MIN_SCALE, (availWidth - FIT_PADDING) / curWidthPt),
    );
  }, [availWidth, curWidthPt]);
  const effScale = fit ? fitScale : manualScale;

  // Load the current PDF once, plus its page dimensions and bookmark outline.
  useEffect(() => {
    const ctl = { cancelled: false };
    const task = pdfjsLib.getDocument({
      url: currentUrl,
      withCredentials: true,
    });
    void (async () => {
      try {
        const doc = await task.promise;
        if (ctl.cancelled) return;
        const dims = await loadPageDims(doc);
        const built = await getOutlineFor(doc);
        // ctl.cancelled is flipped in cleanup; CFA can't see that cross-closure.
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        if (ctl.cancelled) return;
        textCacheRef.current = new Map();
        setCurDoc(doc);
        setPages(dims);
        setOutline(built);
        setMatchPages([]);
        setMatchIdx(0);
        setPage(1);
      } catch {
        // Loading failure surfaces as the "no current PDF" spinner staying put.
      }
    })();
    return () => {
      ctl.cancelled = true;
      void task.destroy();
    };
  }, [currentUrl]);

  // Load the selected base PDF (404 → "no archive" message).
  useEffect(() => {
    const ctl = { cancelled: false };
    const task = baseId
      ? pdfjsLib.getDocument({ url: baseUrlFor(baseId), withCredentials: true })
      : null;
    void (async () => {
      setBaseDoc(null);
      setBaseError(false);
      if (!task) return;
      try {
        const doc = await task.promise;
        if (!ctl.cancelled) setBaseDoc(doc);
      } catch {
        if (!ctl.cancelled) setBaseError(true);
      }
    })();
    return () => {
      ctl.cancelled = true;
      if (task) void task.destroy();
    };
  }, [baseId, baseUrlFor]);

  // Track available width (for fit-to-width); recomputes when the sidebar opens.
  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const measure = () => {
      setAvailWidth(el.clientWidth);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);

  // Render both pages (and the diff) whenever inputs change. Each page.render
  // is tracked so the cleanup can cancel an in-flight raster before the next
  // run starts — without that, rapid page/zoom/mode changes fire concurrent
  // renders on the same (stable-ref) canvas, which pdf.js v6 rejects and which
  // would let computeDiff read a half-painted canvas.
  useEffect(() => {
    if (!curDoc || availWidth === 0) return;
    const ctl: {
      cancelled: boolean;
      curTask: pdfjsLib.RenderTask | null;
      baseTask: pdfjsLib.RenderTask | null;
    } = { cancelled: false, curTask: null, baseTask: null };
    const isCancelled = (): boolean => ctl.cancelled;
    void (async () => {
      const dim = pages[page - 1];
      if (dim)
        setDisp({ w: dim.widthPt * effScale, h: dim.heightPt * effScale });

      const curCanvas = curCanvasRef.current;
      const baseCanvas = baseCanvasRef.current;
      if (!curCanvas) return;

      ctl.curTask = await renderPage(
        curDoc,
        page,
        effScale,
        curCanvas,
        isCancelled,
      );
      await ctl.curTask?.promise.catch(() => undefined);
      // ctl.cancelled flips in cleanup; CFA can't see that cross-closure.

      if (ctl.cancelled || !baseCanvas) return;

      // Render the matching base page, or paint the base white when this page
      // has no counterpart in the (older/shorter, or still-loading) base build.
      if (baseDoc && page <= baseDoc.numPages) {
        ctl.baseTask = await renderPage(
          baseDoc,
          page,
          effScale,
          baseCanvas,
          isCancelled,
        );
        await ctl.baseTask?.promise.catch(() => undefined);
      } else {
        paintBlank(curCanvas, baseCanvas);
      }
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (ctl.cancelled) return;
      if (mode === "diff" && diffCanvasRef.current) {
        setDiffAligned(
          computeDiff(baseCanvas, curCanvas, diffCanvasRef.current),
        );
      }
    })().catch(() => undefined);
    return () => {
      ctl.cancelled = true;
      ctl.curTask?.cancel();
      ctl.baseTask?.cancel();
    };
  }, [curDoc, baseDoc, page, availWidth, mode, effScale, pages]);

  const go = useCallback(
    (n: number) => {
      setPage(Math.min(Math.max(1, n), numPages || 1));
    },
    [numPages],
  );

  useEffect(() => {
    if (!pageFocusedRef.current) setPageDraft(String(page));
  }, [page]);

  useEffect(() => {
    if (!zoomFocusedRef.current)
      setZoomDraft(String(Math.round((effScale / PT_TO_PX) * 100)));
  }, [effScale]);

  const zoomBy = (factor: number): void => {
    setFit(false);
    setManualScale(Math.min(Math.max(effScale * factor, MIN_SCALE), MAX_SCALE));
  };

  const commitPageInput = (): void => {
    const n = Number.parseInt(pageDraft, 10);
    if (Number.isFinite(n) && n >= 1 && n <= numPages) go(n);
    else setPageDraft(String(page));
  };

  const commitZoomInput = (): void => {
    const pct = Number.parseInt(zoomDraft, 10);
    if (Number.isFinite(pct) && pct > 0) {
      const next = Math.min(
        Math.max((pct / 100) * PT_TO_PX, MIN_SCALE),
        MAX_SCALE,
      );
      setFit(false);
      setManualScale(next);
      setZoomDraft(String(Math.round((next / PT_TO_PX) * 100)));
    } else {
      setZoomDraft(String(Math.round((effScale / PT_TO_PX) * 100)));
    }
  };

  // Search the *current* build: collect the pages that contain the query and
  // jump to the first. The canvas render can't paint per-word highlights, so
  // navigation lands on the page — same model as the reader, minus the marks.
  const runSearch = useCallback(async () => {
    const needle = query.trim().toLowerCase();
    if (!curDoc || !needle) {
      setMatchPages([]);
      setMatchIdx(0);
      return;
    }
    const cache = textCacheRef.current;
    const found: number[] = [];
    for (let n = 1; n <= numPages; n++) {
      let text = cache.get(n);
      if (text === undefined) {
        const pg = await curDoc.getPage(n);
        const content = await pg.getTextContent();
        text = content.items
          .map((it) => ("str" in it ? it.str : ""))
          .join(" ")
          .toLowerCase();
        cache.set(n, text);
      }
      const c = countOccurrences(text, needle);
      for (let k = 0; k < c; k++) found.push(n);
    }
    setMatchPages(found);
    setMatchIdx(0);
    const first = found[0];
    if (first != null) go(first);
  }, [curDoc, numPages, query, go]);

  const stepMatch = (delta: number): void => {
    if (matchPages.length === 0) return;
    const next = (matchIdx + delta + matchPages.length) % matchPages.length;
    setMatchIdx(next);
    const p = matchPages[next];
    if (p != null) go(p);
  };

  const pxPerMm = effScale * PT_PER_MM;

  return (
    <div className="pdf-diff" style={{ flex: 1, minHeight: 0 }}>
      <div className="pdf-diff-toolbar">
        <div className="seg">
          <button
            type="button"
            className={
              sidebarOpen && sidebarTab === "outline" ? "active" : undefined
            }
            aria-label={t("sidebar.outline")}
            title={t("sidebar.outline")}
            disabled={outline.length === 0}
            onClick={() => {
              setSidebarOpen((v) => !(v && sidebarTab === "outline"));
              setSidebarTab("outline");
            }}
          >
            <List size={13} />
          </button>
          <button
            type="button"
            className={
              sidebarOpen && sidebarTab === "thumbs" ? "active" : undefined
            }
            aria-label={t("sidebar.thumbnails")}
            title={t("sidebar.thumbnailsTitle")}
            onClick={() => {
              setSidebarOpen((v) => !(v && sidebarTab === "thumbs"));
              setSidebarTab("thumbs");
            }}
          >
            <Images size={13} />
          </button>
        </div>

        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("diff.compareWith")}
        </span>
        <select
          value={baseId}
          onChange={(e) => {
            setBaseId(e.target.value);
          }}
          className="pdf-diff-select"
        >
          {bases.length === 0 && (
            <option value="">{t("diff.noPreviousBuilds")}</option>
          )}
          {bases.map((b) => (
            <option key={b.id} value={b.id}>
              {b.label}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-1">
          <button
            type="button"
            className="icon-btn sm"
            aria-label={t("nav.prevPage")}
            onClick={() => {
              go(page - 1);
            }}
          >
            <ChevronLeft size={13} />
          </button>
          <input
            value={pageDraft}
            onChange={(e) => {
              setPageDraft(e.target.value);
            }}
            onFocus={() => {
              pageFocusedRef.current = true;
            }}
            onBlur={() => {
              pageFocusedRef.current = false;
              commitPageInput();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitPageInput();
            }}
            aria-label={t("nav.pageNumber")}
            style={{
              width: 38,
              textAlign: "center",
              fontSize: 11.5,
              padding: "1px 2px",
              background: "var(--bg-0)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              color: "var(--fg-0)",
            }}
          />
          <span className="dim mono">/ {numPages || "?"}</span>
          <button
            type="button"
            className="icon-btn sm"
            aria-label={t("nav.nextPage")}
            onClick={() => {
              go(page + 1);
            }}
          >
            <ChevronRight size={13} />
          </button>
        </div>

        <div className="seg">
          <button
            type="button"
            aria-label={t("zoom.out")}
            onClick={() => {
              zoomBy(0.8);
            }}
          >
            <Minus size={12} />
          </button>
          <span
            className="mono"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 1,
              padding: "0 6px",
              minWidth: 44,
              justifyContent: "center",
            }}
          >
            <input
              value={zoomDraft}
              onChange={(e) => {
                setZoomDraft(e.target.value);
              }}
              onFocus={(e) => {
                zoomFocusedRef.current = true;
                e.currentTarget.select();
              }}
              onBlur={() => {
                zoomFocusedRef.current = false;
                commitZoomInput();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  commitZoomInput();
                  e.currentTarget.blur();
                }
              }}
              aria-label={t("zoom.percentAria")}
              title={t("zoom.percentTitle")}
              inputMode="numeric"
              style={{
                width: 26,
                textAlign: "right",
                fontSize: 11.5,
                fontFamily: "inherit",
                padding: 0,
                background: "transparent",
                border: 0,
                outline: "none",
                color: "var(--fg-0)",
              }}
            />
            <span style={{ color: "var(--fg-2)" }}>%</span>
          </span>
          <button
            type="button"
            aria-label={t("zoom.in")}
            onClick={() => {
              zoomBy(1.25);
            }}
          >
            <Plus size={12} />
          </button>
          <button
            type="button"
            className={fit ? "active" : ""}
            aria-label={t("zoom.fitWidth")}
            title={t("zoom.fitWidth")}
            onClick={() => {
              setFit(true);
            }}
          >
            <Scan size={12} />
          </button>
        </div>

        <div className="seg">
          <button
            type="button"
            className={mode === "diff" ? "active" : ""}
            title={t("diff.modeDiffTitle")}
            onClick={() => {
              setMode("diff");
            }}
          >
            <Contrast size={12} />
          </button>
          <button
            type="button"
            className={mode === "fade" ? "active" : ""}
            title={t("diff.modeFadeTitle")}
            onClick={() => {
              setMode("fade");
            }}
          >
            <Layers size={12} />
          </button>
          <button
            type="button"
            className={mode === "swipe" ? "active" : ""}
            title={t("diff.modeSwipeTitle")}
            onClick={() => {
              setMode("swipe");
            }}
          >
            <Columns2 size={12} />
          </button>
        </div>

        {mode === "swipe" && (
          <input
            type="range"
            min={0}
            max={100}
            value={swipe}
            onChange={(e) => {
              setSwipe(Number(e.target.value));
            }}
            aria-label={t("diff.swipePositionAria")}
            style={{ width: 110 }}
          />
        )}
        {mode === "fade" && (
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(fade * 100)}
            onChange={(e) => {
              setFade(Number(e.target.value) / 100);
            }}
            aria-label={t("diff.opacityAria")}
            style={{ width: 110 }}
          />
        )}
        {mode === "diff" && (
          <span className="dim mono" style={{ fontSize: 10.5 }}>
            <span style={{ color: "rgb(38,166,74)" }}>■</span> {t("diff.added")}{" "}
            <span style={{ color: "rgb(208,52,52)" }}>■</span>{" "}
            {t("diff.removed")}
          </span>
        )}

        <div className="seg">
          {marginGuideMm && (
            <button
              type="button"
              className={guidesOn ? "active" : ""}
              aria-label={t("tools.gostMargins")}
              title={t("tools.gostMarginsTitle")}
              onClick={() => {
                setGuidesOn((v) => !v);
              }}
            >
              <Frame size={12} />
            </button>
          )}
          <button
            type="button"
            className={measureMode ? "active" : ""}
            aria-label={t("tools.ruler")}
            title={t("tools.rulerTitle")}
            onClick={() => {
              setMeasureMode((v) => !v);
            }}
          >
            <Ruler size={12} />
          </button>
          <button
            type="button"
            className={invert ? "active" : ""}
            aria-label={t("tools.nightMode")}
            title={t("tools.nightModeTitle")}
            onClick={() => {
              setInvert((v) => !v);
            }}
          >
            <Moon size={12} />
          </button>
          <button
            type="button"
            aria-label={t("tools.print")}
            title={t("tools.printDiffTitle")}
            onClick={() => {
              window.open(currentUrl, "_blank", "noopener");
            }}
          >
            <Printer size={12} />
          </button>
        </div>

        <form
          className="flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            void runSearch();
          }}
        >
          <div
            className="flex items-center gap-1"
            style={{
              background: "var(--bg-0)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "3px 8px",
            }}
          >
            <Search size={13} style={{ color: "var(--fg-3)" }} />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
              placeholder={t("search.placeholder")}
              aria-label={t("search.aria")}
              style={{
                width: 150,
                fontSize: 12.5,
                background: "transparent",
                border: 0,
                outline: "none",
                color: "var(--fg-0)",
              }}
            />
          </div>
          {matchPages.length > 0 && (
            <>
              <span className="dim mono" style={{ whiteSpace: "nowrap" }}>
                {matchIdx + 1}/{matchPages.length}
              </span>
              <button
                type="button"
                className="icon-btn sm"
                aria-label={t("search.prevMatch")}
                onClick={() => {
                  stepMatch(-1);
                }}
              >
                <ChevronLeft size={12} />
              </button>
              <button
                type="button"
                className="icon-btn sm"
                aria-label={t("search.nextMatch")}
                onClick={() => {
                  stepMatch(1);
                }}
              >
                <ChevronRight size={12} />
              </button>
            </>
          )}
        </form>

        <button
          type="button"
          className="icon-btn sm"
          aria-label={t("diff.close")}
          title={t("diff.close")}
          onClick={onClose}
          style={{ marginLeft: "auto" }}
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex" style={{ flex: 1, minHeight: 0 }}>
        {sidebarOpen && (
          <div
            style={{
              width: sidebarTab === "thumbs" ? 168 : 240,
              flexShrink: 0,
              overflowY: "auto",
              borderRight: "1px solid var(--border)",
              background: "var(--bg-1)",
              padding: "6px 4px",
            }}
          >
            {sidebarTab === "outline" && outline.length > 0 && (
              <PdfOutline entries={outline} onJump={go} />
            )}
            {sidebarTab === "thumbs" && curDoc && (
              <PdfThumbnails
                pdf={curDoc}
                pages={pages}
                currentPage={page}
                onJump={go}
              />
            )}
          </div>
        )}

        <div ref={areaRef} className="pdf-diff-area">
          {!curDoc && (
            <div style={{ padding: 40 }}>
              <Spinner />
            </div>
          )}
          {curDoc && baseError && (
            <div
              className="dim"
              style={{ padding: 24, fontSize: 12.5, maxWidth: 420 }}
            >
              {t("diff.noArchive")}
            </div>
          )}
          {curDoc && !baseError && (
            <div
              className="pdf-diff-stage"
              style={{
                width: disp.w || undefined,
                height: disp.h || undefined,
              }}
            >
              <canvas
                ref={baseCanvasRef}
                className={
                  invert ? "pdf-diff-canvas pdf-invert" : "pdf-diff-canvas"
                }
              />
              <canvas
                ref={curCanvasRef}
                className={
                  invert ? "pdf-diff-canvas pdf-invert" : "pdf-diff-canvas"
                }
                style={{
                  zIndex: 2,
                  opacity: mode === "fade" ? fade : 1,
                  clipPath:
                    mode === "swipe"
                      ? `inset(0 ${String(100 - swipe)}% 0 0)`
                      : "none",
                  visibility: mode === "diff" ? "hidden" : "visible",
                }}
              />
              <canvas
                ref={diffCanvasRef}
                className="pdf-diff-canvas"
                style={{
                  zIndex: 3,
                  width: disp.w || undefined,
                  height: disp.h || undefined,
                  display: mode === "diff" ? "block" : "none",
                }}
              />
              {guidesOn && marginGuideMm && (
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
              {mode === "swipe" && (
                <div
                  className="pdf-diff-handle"
                  style={{ left: `${String(swipe)}%` }}
                />
              )}
              {measureMode && <MeasureOverlay pxPerMm={pxPerMm} />}
              {mode === "diff" && !diffAligned && (
                <div className="pdf-diff-warn">{t("diff.sizeChangedWarn")}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
