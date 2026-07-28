import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  FileSearch,
  Frame,
  Images,
  List,
  Minus,
  Moon,
  Plus,
  Printer,
  Ruler,
  Scan,
  Search,
  Sparkles,
} from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
// Vite resolves this to a hashed asset URL for the worker bundle (kept out of
// the main chunk); pdfjs finds it at runtime via GlobalWorkerOptions.workerSrc.
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { Spinner } from "../Spinner";
import {
  PdfPage,
  type PageDim,
  type PageMargins,
  type PdfStamp,
} from "./PdfPage";
import { PdfThumbnails } from "./PdfThumbnails";
import { PdfOutline, type OutlineEntry } from "./PdfOutline";
import { countOccurrences, getOutlineFor, loadPageDims } from "./pdfDoc";
import "./pdfViewer.css";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const PT_TO_PX = 96 / 72;
// Zoom a freshly opened document (no remembered scale) starts at. 100% is the
// natural PT_TO_PX size; 0.9 opens it a touch smaller so the whole page width
// fits comfortably without fit-to-width stretching.
const DEFAULT_SCALE = PT_TO_PX * 0.9;
const MIN_SCALE = 0.2;
const MAX_SCALE = 5;
const PAGE_GAP = 12;
const FIT_PADDING = 24;

type Persisted = { scale: number; fit: boolean; page: number };

const readPersist = (key: string | undefined): Persisted | null => {
  if (!key) return null;
  try {
    const raw = localStorage.getItem(`pdfview:${key}`);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<Persisted>;
    if (typeof v.scale !== "number" || typeof v.page !== "number") return null;
    return { scale: v.scale, fit: v.fit !== false, page: v.page };
  } catch {
    return null;
  }
};

const writePersist = (key: string | undefined, v: Persisted): void => {
  if (!key) return;
  try {
    localStorage.setItem(`pdfview:${key}`, JSON.stringify(v));
  } catch {
    // Storage may be unavailable (private mode / quota) — non-fatal.
  }
};

export type PdfViewerProps = {
  url: string;
  refreshKey?: string | number;
  toolbarExtras?: ReactNode;
  className?: string;
  ariaLabel?: string;
  /** Stamps (e.g. signatures) drawn cleanly over the pages they belong to. */
  stamps?: PdfStamp[];
  /** When set, the GOST margin guide can be toggled on (drawn on every page). */
  marginGuideMm?: PageMargins;
  /** Stable id (e.g. project+doc) used to remember page/zoom across opens. */
  storageKey?: string;
  /** Ctrl/Cmd+click on a page → (page, x, y in PDF points) for SyncTeX inverse. */
  onInverseSync?: (page: number, xPt: number, yPt: number) => void;
  /** Selected PDF text → send to the agent (shows a button on selection). */
  onAskAgent?: (text: string) => void;
  /** Selected PDF text → locate it in the source editor. */
  onFindInSource?: (text: string) => void;
  /** SyncTeX forward target: scroll there + flash. `token` re-fires on repeat. */
  jump?: {
    page: number;
    xPt: number;
    yPt: number;
    widthPt: number;
    heightPt: number;
    token: number;
  } | null;
};

export const PdfViewer = ({
  url,
  refreshKey,
  toolbarExtras,
  className,
  ariaLabel,
  stamps,
  marginGuideMm,
  storageKey,
  onInverseSync,
  jump,
  onAskAgent,
  onFindInSource,
}: PdfViewerProps) => {
  const { t } = useTranslation("pdfViewer");
  const rootRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const pageInputRef = useRef<HTMLInputElement>(null);
  const scrollRatioRef = useRef(0);
  const restoreRef = useRef(false);
  const firstRef = useRef(true);
  const didRestorePageRef = useRef(false);
  const textCacheRef = useRef<Map<number, string>>(new Map());
  const pageFocusedRef = useRef(false);
  const zoomFocusedRef = useRef(false);
  const appliedJumpRef = useRef<number | undefined>(undefined);
  const scaleRef = useRef(DEFAULT_SCALE);

  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PageDim[]>([]);
  const [outline, setOutline] = useState<OutlineEntry[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [scale, setScale] = useState(
    () => readPersist(storageKey)?.scale ?? DEFAULT_SCALE,
  );
  // Default to DEFAULT_SCALE (90%) rather than fit-to-width, which stretches an
  // A4 page to the pane and lands around 115%. A remembered choice still wins;
  // the "По ширине" button re-enables fit on demand.
  const [fit, setFit] = useState(() => readPersist(storageKey)?.fit ?? false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageDraft, setPageDraft] = useState("1");
  const [zoomDraft, setZoomDraft] = useState(() =>
    String(
      Math.round(
        ((readPersist(storageKey)?.scale ?? DEFAULT_SCALE) / PT_TO_PX) * 100,
      ),
    ),
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<"outline" | "thumbs">("outline");
  const [invert, setInvert] = useState(false);
  const [guidesOn, setGuidesOn] = useState(false);
  const [measureMode, setMeasureMode] = useState(false);

  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [matchPages, setMatchPages] = useState<number[]>([]);
  const [matchIdx, setMatchIdx] = useState(0);

  // Floating action bar shown above a non-empty text selection in the PDF.
  const [selAction, setSelAction] = useState<{
    text: string;
    left: number;
    top: number;
  } | null>(null);

  const fetchUrl =
    refreshKey != null
      ? `${url}${url.includes("?") ? "&" : "?"}v=${encodeURIComponent(String(refreshKey))}`
      : url;

  useEffect(() => {
    const ctl: { cancelled: boolean } = { cancelled: false };
    const task = pdfjsLib.getDocument({ url: fetchUrl, withCredentials: true });
    void (async () => {
      setStatus("loading");
      textCacheRef.current = new Map();
      try {
        const doc = await task.promise;
        if (ctl.cancelled) return;
        const dims = await loadPageDims(doc);
        const built = await getOutlineFor(doc);
        // ctl.cancelled is flipped in cleanup; CFA can't see that cross-closure.
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        if (ctl.cancelled) return;
        setPdf(doc);
        setPages(dims);
        setOutline(built);
        setStatus("ready");
        if (!firstRef.current) restoreRef.current = true;
        firstRef.current = false;
      } catch {
        if (!ctl.cancelled) setStatus("error");
      }
    })();
    return () => {
      ctl.cancelled = true;
      void task.destroy();
    };
  }, [fetchUrl]);

  const computeFit = useCallback(() => {
    const el = scrollRef.current;
    if (!el || pages.length === 0) return;
    const maxW = Math.max(...pages.map((p) => p.widthPt));
    const next = (el.clientWidth - FIT_PADDING) / maxW;
    setScale(Math.min(Math.max(next, MIN_SCALE), MAX_SCALE));
  }, [pages]);

  useEffect(() => {
    if (fit) computeFit();
  }, [fit, computeFit]);

  useEffect(() => {
    if (!fit) return;
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      computeFit();
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [fit, computeFit]);

  useEffect(() => {
    if (status !== "ready" || !restoreRef.current) return;
    restoreRef.current = false;
    const el = scrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      const max = el.scrollHeight - el.clientHeight;
      el.scrollTop = scrollRatioRef.current * (max > 0 ? max : 0);
    });
  }, [status, pages, scale]);

  useEffect(() => {
    if (!pageFocusedRef.current) setPageDraft(String(currentPage));
  }, [currentPage]);

  // Keep the editable zoom field showing the live percentage unless the user is
  // mid-edit (e.g. when +/-, fit-to-width or a remembered scale changes it).
  useEffect(() => {
    if (!zoomFocusedRef.current)
      setZoomDraft(String(Math.round((scale / PT_TO_PX) * 100)));
  }, [scale]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setSelAction(null);
    const max = el.scrollHeight - el.clientHeight;
    scrollRatioRef.current = max > 0 ? el.scrollTop / max : 0;
    const mid = el.scrollTop + el.clientHeight / 2;
    let acc = FIT_PADDING / 2;
    for (const p of pages) {
      acc += p.heightPt * scale + PAGE_GAP;
      if (acc >= mid) {
        setCurrentPage(p.num);
        break;
      }
    }
  }, [pages, scale]);

  // After a drag-select in the PDF, float an action bar above the selection.
  const refreshSelectionBar = useCallback(() => {
    if (!onAskAgent && !onFindInSource) return;
    const sel = window.getSelection();
    const root = rootRef.current;
    const scroll = scrollRef.current;
    if (!sel || sel.isCollapsed || !root || !scroll) {
      setSelAction(null);
      return;
    }
    const text = sel.toString().trim();
    const anchor = sel.anchorNode;
    if (text.length < 2 || !anchor || !scroll.contains(anchor)) {
      setSelAction(null);
      return;
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const rootRect = root.getBoundingClientRect();
    setSelAction({
      text,
      left: rect.left - rootRect.left + rect.width / 2,
      top: rect.top - rootRect.top,
    });
  }, [onAskAgent, onFindInSource]);

  const askAgentSelection = (): void => {
    if (selAction) onAskAgent?.(selAction.text);
    setSelAction(null);
  };
  const findSelectionInSource = (): void => {
    if (selAction) onFindInSource?.(selAction.text);
    setSelAction(null);
  };
  const copySelection = (): void => {
    if (selAction)
      void navigator.clipboard.writeText(selAction.text).catch(() => undefined);
    setSelAction(null);
  };

  const goToPage = useCallback((n: number) => {
    const el = scrollRef.current;
    if (!el) return;
    const target = el.querySelector<HTMLElement>(`[data-page="${String(n)}"]`);
    if (target) target.scrollIntoView({ block: "start", behavior: "smooth" });
  }, []);

  // Reads scale via a ref so its identity is stable — the jump effect can defer
  // the scroll a frame (until fit-to-width has settled the scale) and still use
  // the final value.
  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);

  const goToPosition = useCallback((page: number, yPt: number) => {
    const el = scrollRef.current;
    if (!el) return;
    const target = el.querySelector<HTMLElement>(
      `[data-page="${String(page)}"]`,
    );
    if (!target) return;
    const top =
      el.scrollTop +
      (target.getBoundingClientRect().top - el.getBoundingClientRect().top) +
      yPt * scaleRef.current -
      80;
    el.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, []);

  // SyncTeX forward jump. Switching to the preview tab can remount this viewer,
  // so the jump must wait for the pages to lay out (status ready + the target
  // page element present) rather than firing once on mount into an empty list.
  // Applying it also suppresses the page-restore so it can't clobber the jump.
  useEffect(() => {
    if (!jump || status !== "ready") return;
    if (appliedJumpRef.current === jump.token) return;
    const el = scrollRef.current;
    if (!el?.querySelector(`[data-page="${String(jump.page)}"]`)) return;
    appliedJumpRef.current = jump.token;
    didRestorePageRef.current = true;
    // Defer a beat so fit-to-width has settled the scale before we measure.
    const id = window.setTimeout(() => {
      goToPosition(jump.page, jump.yPt);
    }, 140);
    return () => {
      window.clearTimeout(id);
    };
  }, [jump, status, pages, goToPosition]);

  const zoomBy = (factor: number): void => {
    setFit(false);
    setScale((s) => Math.min(Math.max(s * factor, MIN_SCALE), MAX_SCALE));
  };

  const commitPageInput = (): void => {
    const n = Number.parseInt(pageDraft, 10);
    if (Number.isFinite(n) && n >= 1 && n <= pages.length) goToPage(n);
    else setPageDraft(String(currentPage));
  };

  // Apply a typed zoom percentage (e.g. 90 → 0.9 × PT_TO_PX), clamped to the
  // allowed range; leaving fit-to-width since this is an explicit scale.
  const commitZoomInput = (): void => {
    const pct = Number.parseInt(zoomDraft, 10);
    if (Number.isFinite(pct) && pct > 0) {
      const next = Math.min(
        Math.max((pct / 100) * PT_TO_PX, MIN_SCALE),
        MAX_SCALE,
      );
      setFit(false);
      setScale(next);
      setZoomDraft(String(Math.round((next / PT_TO_PX) * 100)));
    } else {
      setZoomDraft(String(Math.round((scale / PT_TO_PX) * 100)));
    }
  };

  const runSearch = useCallback(async () => {
    const needle = query.trim().toLowerCase();
    setSubmittedQuery(needle);
    if (!pdf || !needle) {
      setMatchPages([]);
      setMatchIdx(0);
      return;
    }
    const cache = textCacheRef.current;
    const found: number[] = [];
    for (let n = 1; n <= pages.length; n++) {
      let text = cache.get(n);
      if (text === undefined) {
        const page = await pdf.getPage(n);
        const content = await page.getTextContent();
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
    if (first != null) goToPage(first);
  }, [pdf, pages.length, query, goToPage]);

  const stepMatch = (delta: number): void => {
    if (matchPages.length === 0) return;
    const next = (matchIdx + delta + matchPages.length) % matchPages.length;
    setMatchIdx(next);
    const page = matchPages[next];
    if (page != null) goToPage(page);
  };

  // Scope Ctrl/Cmd+A (select PDF text) and Ctrl/Cmd+F (PDF search) to the
  // viewer. A document-level listener in the capture phase reliably pre-empts
  // the browser/IDE defaults, and we gate it on focus being inside the scroll
  // area — so these keys behave normally everywhere else in the IDE. The area
  // is focused on pointer-down (clicking selectable text doesn't always move
  // focus to a tabindex container by itself), which is what makes the gate true.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
      const key = e.key.toLowerCase();
      if (key !== "a" && key !== "f" && key !== "g") return;
      const el = scrollRef.current;
      if (!el?.contains(document.activeElement)) return;
      if (key === "a") {
        const sel = window.getSelection();
        const layers = el.querySelectorAll<HTMLElement>(".textLayer");
        const first = layers[0];
        const last = layers[layers.length - 1];
        if (!sel || !first || !last) return;
        e.preventDefault();
        e.stopPropagation();
        const range = document.createRange();
        range.setStartBefore(first);
        range.setEndAfter(last);
        sel.removeAllRanges();
        sel.addRange(range);
      } else if (key === "f") {
        e.preventDefault();
        e.stopPropagation();
        const input = searchInputRef.current;
        if (input) {
          input.focus();
          input.select();
        }
      } else {
        // Ctrl/Cmd+G — jump to the page-number box.
        e.preventDefault();
        e.stopPropagation();
        const input = pageInputRef.current;
        if (input) {
          input.focus();
          input.select();
        }
      }
    };
    document.addEventListener("keydown", onKey, { capture: true });
    return () => {
      document.removeEventListener("keydown", onKey, { capture: true });
    };
  }, []);

  // Plain (non-modifier) keys when the viewer holds focus: zoom and fit. Page
  // scrolling (arrows, space, PageUp/Down, Home/End) is left to the native
  // focusable scroll container, so we only add what the browser doesn't give.
  useEffect(() => {
    const onNav = (e: KeyboardEvent): void => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const el = scrollRef.current;
      if (!el?.contains(document.activeElement)) return;
      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setFit(false);
        setScale((s) => Math.min(Math.max(s * 1.25, MIN_SCALE), MAX_SCALE));
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        setFit(false);
        setScale((s) => Math.min(Math.max(s * 0.8, MIN_SCALE), MAX_SCALE));
      } else if (e.key === "0") {
        e.preventDefault();
        setFit(true);
      }
    };
    document.addEventListener("keydown", onNav);
    return () => {
      document.removeEventListener("keydown", onNav);
    };
  }, []);

  // Remember page/zoom per document, and restore the page on the first open.
  useEffect(() => {
    if (status === "ready")
      writePersist(storageKey, { scale, fit, page: currentPage });
  }, [storageKey, status, scale, fit, currentPage]);

  useEffect(() => {
    if (status !== "ready" || didRestorePageRef.current) return;
    didRestorePageRef.current = true;
    const saved = readPersist(storageKey)?.page;
    if (!saved || saved <= 1) return;
    const el = scrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      const target = el.querySelector<HTMLElement>(
        `[data-page="${String(saved)}"]`,
      );
      target?.scrollIntoView({ block: "start" });
    });
  }, [status, storageKey, pages]);

  return (
    <div
      ref={rootRef}
      className={className}
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        flex: 1,
      }}
      aria-label={ariaLabel}
    >
      <div
        className="flex items-center"
        style={{
          padding: "6px 10px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
          fontSize: 11.5,
          gap: 8,
          flexShrink: 0,
          flexWrap: "wrap",
        }}
      >
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

        <div className="flex items-center gap-1">
          <button
            type="button"
            className="icon-btn sm"
            aria-label={t("nav.prevPage")}
            onClick={() => {
              goToPage(Math.max(1, currentPage - 1));
            }}
          >
            <ChevronLeft size={13} />
          </button>
          <input
            ref={pageInputRef}
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
          <span className="dim mono">/ {pages.length}</span>
          <button
            type="button"
            className="icon-btn sm"
            aria-label={t("nav.nextPage")}
            onClick={() => {
              goToPage(Math.min(pages.length, currentPage + 1));
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
            onClick={() => {
              setFit(true);
            }}
          >
            <Scan size={12} />
          </button>
        </div>

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
            title={t("tools.printTitle")}
            onClick={() => {
              window.open(fetchUrl, "_blank", "noopener");
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
              ref={searchInputRef}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
              placeholder={t("search.placeholderWithShortcut")}
              aria-label={t("search.aria")}
              style={{
                width: 210,
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

        <div
          className="flex items-center gap-2 shrink-0"
          style={{ marginLeft: "auto" }}
        >
          {toolbarExtras}
        </div>
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
              <PdfOutline
                entries={outline}
                onJump={(n) => {
                  goToPage(n);
                }}
              />
            )}
            {sidebarTab === "thumbs" && pdf && (
              <PdfThumbnails
                pdf={pdf}
                pages={pages}
                currentPage={currentPage}
                onJump={(n) => {
                  goToPage(n);
                }}
              />
            )}
          </div>
        )}

        <div
          ref={scrollRef}
          onScroll={onScroll}
          onMouseDown={() => {
            // Ensure the viewer owns focus so Ctrl+A / Ctrl+F target the PDF.
            scrollRef.current?.focus({ preventScroll: true });
            setSelAction(null);
          }}
          onMouseUp={() => {
            // Defer a frame so the browser has finalised the selection.
            requestAnimationFrame(refreshSelectionBar);
          }}
          tabIndex={0}
          role="document"
          aria-label={t("content.aria")}
          style={{
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            background: "var(--bg-0)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: PAGE_GAP,
            padding: FIT_PADDING / 2,
            outline: "none",
          }}
        >
          {status === "loading" && (
            <div className="flex justify-center" style={{ padding: 40 }}>
              <Spinner />
            </div>
          )}
          {status === "error" && (
            <div className="dim" style={{ padding: 24, fontSize: 12.5 }}>
              {t("content.loadError")}
            </div>
          )}
          {status === "ready" &&
            pdf &&
            pages.map((dim) => (
              <PdfPage
                key={`${fetchUrl}#${String(dim.num)}`}
                pdf={pdf}
                dim={dim}
                scale={scale}
                searchQuery={submittedQuery}
                stamps={stamps?.filter((s) => s.page === dim.num)}
                invert={invert}
                marginGuideMm={guidesOn ? marginGuideMm : null}
                measureMode={measureMode}
                onLinkClick={goToPage}
                onInverseClick={onInverseSync}
                flash={
                  jump?.page === dim.num
                    ? {
                        xPt: jump.xPt,
                        yPt: jump.yPt,
                        widthPt: jump.widthPt,
                        heightPt: jump.heightPt,
                        token: jump.token,
                      }
                    : null
                }
              />
            ))}
        </div>
      </div>

      {selAction && (
        <div
          className="pdf-sel-bar"
          style={{ left: selAction.left, top: selAction.top }}
          onMouseDown={(e) => {
            // Don't let the bar's own mousedown clear the selection/bar.
            e.preventDefault();
          }}
        >
          {onAskAgent && (
            <button type="button" onClick={askAgentSelection}>
              <Sparkles size={12} />
              {t("selection.askAgent")}
            </button>
          )}
          {onFindInSource && (
            <button type="button" onClick={findSelectionInSource}>
              <FileSearch size={12} />
              {t("selection.findInSource")}
            </button>
          )}
          <button type="button" onClick={copySelection}>
            <Copy size={12} />
            {t("selection.copy")}
          </button>
        </div>
      )}
    </div>
  );
};
