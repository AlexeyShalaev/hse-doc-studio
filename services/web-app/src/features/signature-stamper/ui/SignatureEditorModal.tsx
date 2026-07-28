import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import {
  Crop,
  Eraser,
  ImagePlus,
  RotateCcw,
  RotateCw,
  Scissors,
  Undo2,
  Redo2,
  RefreshCcw,
  Upload,
  Wand,
  Wand2,
  X as XIcon,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import {
  DEFAULT_SOFTNESS,
  imageDataToPngFile,
  otsuThreshold,
  removeBackground,
} from "../lib/bgRemoval";
import {
  autoTrim,
  blobToImageData,
  cloneImageData,
  cropImageData,
  eraseCircleInPlace,
  imageFromDataTransfer,
  magicErase,
  readClipboardImage,
  rotate90,
} from "../lib/imageOps";

export type SignatureEditorModalProps = {
  initialFile: File | null;
  // When editing an existing signature: URL of the current PNG to load in.
  initialUrl?: string | null;
  slotLabel: string;
  isUploading?: boolean;
  onCancel: () => void;
  onConfirm: (file: File) => void;
};

type Tool = "none" | "bg" | "erase" | "magic" | "crop";
type Recolor = "keep" | "black" | "blue";
type Rect = { x: number; y: number; w: number; h: number };

const RECOLOR_HEX: Record<Recolor, string | null> = {
  keep: null,
  black: "#101010",
  blue: "#0a1e78",
};

const PREVIEW_H = 320;
const PREVIEW_PAD = 12;
const MAX_SCALE = 3;
const MAX_HISTORY = 40;
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 8;
const ZOOM_STEP = 1.25; // per button press
const WHEEL_STEP = 1.12; // per wheel notch (finer than buttons)

const clamp = (v: number, lo: number, hi: number): number =>
  Math.min(hi, Math.max(lo, v));
const clampZoom = (z: number): number => clamp(z, ZOOM_MIN, ZOOM_MAX);

const normalizeRect = (r: Rect): Rect => ({
  x: r.w < 0 ? r.x + r.w : r.x,
  y: r.h < 0 ? r.y + r.h : r.y,
  w: Math.abs(r.w),
  h: Math.abs(r.h),
});

export const SignatureEditorModal = ({
  initialFile,
  initialUrl,
  slotLabel,
  isUploading,
  onCancel,
  onConfirm,
}: SignatureEditorModalProps) => {
  const { t } = useTranslation("signatureStamper");
  const [history, setHistory] = useState<ImageData[]>([]);
  const [idx, setIdx] = useState(-1);
  const [tool, setTool] = useState<Tool>("none");
  const [threshold, setThreshold] = useState(200);
  const [softness, setSoftness] = useState(DEFAULT_SOFTNESS);
  const [recolor, setRecolor] = useState<Recolor>("keep");
  const [brush, setBrush] = useState(28);
  const [magicTol, setMagicTol] = useState(30);
  const [magicContiguous, setMagicContiguous] = useState(true);
  const [cropRect, setCropRect] = useState<Rect | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [availW, setAvailW] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const eraseRef = useRef<ImageData | null>(null);
  const drawingRef = useRef(false);
  const cropStartRef = useRef<{ x: number; y: number } | null>(null);
  // Drag-to-pan origin (screen point + scroll offset) for the hand tool.
  const panRef = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const [tick, bump] = useReducer((c: number) => c + 1, 0);

  const current = idx >= 0 ? (history[idx] ?? null) : null;
  const hasImage = current != null;
  const uploading = isUploading ?? false;
  const baseName = initialFile?.name ?? "signature.png";

  // ── load an image (file / clipboard / drop) ──────────────────────────────
  const loadBlob = useCallback((blob: Blob) => {
    blobToImageData(blob)
      .then((data) => {
        setHistory([data]);
        setIdx(0);
        setTool("none");
        setZoom(1);
        setError(null);
      })
      .catch((e: unknown) => {
        setError(String(e));
      });
  }, []);

  useEffect(() => {
    if (initialFile) {
      loadBlob(initialFile);
      return;
    }
    if (initialUrl) {
      void fetch(initialUrl)
        .then((r) => r.blob())
        .then((b) => {
          loadBlob(b);
        })
        .catch((e: unknown) => {
          setError(String(e));
        });
    }
  }, [initialFile, initialUrl, loadBlob]);

  // Paste anywhere while the editor is open.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const f = imageFromDataTransfer(e.clipboardData);
      if (f) {
        e.preventDefault();
        loadBlob(f);
      }
    };
    window.addEventListener("paste", onPaste);
    return () => {
      window.removeEventListener("paste", onPaste);
    };
  }, [loadBlob]);

  // Measure the stage width so the canvas can be scaled to fit.
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const measure = () => {
      setAvailW(Math.max(0, el.clientWidth - PREVIEW_PAD * 2));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [hasImage]);

  const fitScale = useMemo(() => {
    if (!current || availW <= 0) return 1;
    const fit = Math.min(
      availW / current.width,
      (PREVIEW_H - PREVIEW_PAD * 2) / current.height,
    );
    return Math.min(fit, MAX_SCALE);
  }, [current, availW]);
  // Effective on-screen scale = auto-fit baseline × user zoom (1 = fit window).
  const scale = fitScale * zoom;
  // The canvas overflows the stage (so the hand tool can pan) only when its
  // scaled size exceeds the usable viewport in at least one axis.
  const pannable =
    current != null &&
    availW > 0 &&
    (current.width * scale > availW + 0.5 ||
      current.height * scale > PREVIEW_H - PREVIEW_PAD * 2 + 0.5);

  // Paint the active image onto the canvas. The active image is `current`
  // (committed history) unless an eraser stroke is in progress.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const data = eraseRef.current ?? current;
    if (!data) return;
    canvas.width = data.width;
    canvas.height = data.height;
    canvas.getContext("2d")?.putImageData(data, 0, 0);
    canvas.style.width = `${String(data.width * scale)}px`;
    canvas.style.height = `${String(data.height * scale)}px`;
  }, [current, scale, tick]);

  // ── zoom / pan ─────────────────────────────────────────────────────────────
  // Zoom is a multiplier on top of the auto-fit scale (1 = fit to window). Once
  // it grows the canvas past the stage the stage scrolls. Each step is anchored
  // to a screen point — the cursor for wheel, the viewport centre for buttons —
  // and we adjust scroll so that point stays put, reading live rects so it works
  // regardless of how the flex container centres the canvas.
  const applyZoom = (rawZoom: number, clientX: number, clientY: number) => {
    const next = clampZoom(rawZoom);
    // The eraser ring and crop selection are stored in overlay display-space and
    // are only refreshed on pointer events, so they go stale when the view
    // rescales under them. Drop them here; both re-appear on the next pointer
    // interaction (and a kept crop rect would otherwise map to the wrong region).
    setCursor(null);
    setCropRect(null);
    cropStartRef.current = null;
    const sc = scrollRef.current;
    const ov = overlayRef.current;
    const canvas = canvasRef.current;
    const img = current;
    if (!sc || !ov || !canvas || !img) {
      setZoom(next);
      return;
    }
    const scRect = sc.getBoundingClientRect();
    const before = ov.getBoundingClientRect();
    const fx =
      before.width > 0
        ? clamp((clientX - before.left) / before.width, 0, 1)
        : 0.5;
    const fy =
      before.height > 0
        ? clamp((clientY - before.top) / before.height, 0, 1)
        : 0.5;
    const vx = clientX - scRect.left;
    const vy = clientY - scRect.top;
    const newScale = fitScale * next;
    const newW = img.width * newScale;
    const newH = img.height * newScale;
    // Resize the canvas now so the scroll metrics read below are up to date.
    canvas.style.width = `${String(newW)}px`;
    canvas.style.height = `${String(newH)}px`;
    const after = ov.getBoundingClientRect();
    const overlayLeft = after.left - scRect.left + sc.scrollLeft;
    const overlayTop = after.top - scRect.top + sc.scrollTop;
    sc.scrollLeft = clamp(
      overlayLeft + fx * newW - vx,
      0,
      sc.scrollWidth - sc.clientWidth,
    );
    sc.scrollTop = clamp(
      overlayTop + fy * newH - vy,
      0,
      sc.scrollHeight - sc.clientHeight,
    );
    setZoom(next);
  };

  const zoomFromCenter = (rawZoom: number) => {
    const sc = scrollRef.current;
    if (!sc) {
      setZoom(clampZoom(rawZoom));
      return;
    }
    const r = sc.getBoundingClientRect();
    applyZoom(rawZoom, r.left + r.width / 2, r.top + r.height / 2);
  };

  // Ctrl/Cmd + wheel zooms toward the cursor; a plain wheel scrolls natively.
  // A native non-passive listener is required so preventDefault() actually
  // suppresses the browser's page zoom. The ref keeps the latest closure so the
  // handler always sees the current zoom without re-binding the listener.
  const wheelRef = useRef<(e: WheelEvent) => void>(() => {
    // replaced with the live handler by the effect below
  });
  useEffect(() => {
    wheelRef.current = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const factor = e.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP;
      applyZoom(zoom * factor, e.clientX, e.clientY);
    };
  });
  useEffect(() => {
    const sc = scrollRef.current;
    if (!sc) return;
    const onWheel = (e: WheelEvent) => {
      wheelRef.current(e);
    };
    sc.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      sc.removeEventListener("wheel", onWheel);
    };
  }, [hasImage]);

  // ── history ──────────────────────────────────────────────────────────────
  const pushImage = (next: ImageData) => {
    setHistory((h) => {
      const trimmed = h.slice(Math.max(0, idx + 2 - MAX_HISTORY), idx + 1);
      return [...trimmed, next];
    });
    setIdx((i) => Math.min(i + 1, MAX_HISTORY - 1));
  };
  const canUndo = idx > 0;
  const canRedo = idx >= 0 && idx < history.length - 1;
  // Only the bg tool needs closing on undo/redo (its in-place tuning assumes
  // the bg step is the history top); erase/crop stay selected and configured.
  const undo = () => {
    if (tool === "bg") setTool("none");
    if (canUndo) setIdx((i) => i - 1);
  };
  const redo = () => {
    if (tool === "bg") setTool("none");
    if (canRedo) setIdx((i) => i + 1);
  };
  const reset = () => {
    if (history.length === 0) return;
    setHistory((h) => h.slice(0, 1));
    setIdx(0);
    setTool("none");
  };

  // ── one-shot ops ─────────────────────────────────────────────────────────
  const applyAutoTrim = () => {
    if (tool === "bg") setTool("none");
    if (current) pushImage(autoTrim(current));
  };
  const applyRotate = (dir: "cw" | "ccw") => {
    if (tool === "bg") setTool("none");
    if (current) pushImage(rotate90(current, dir));
  };

  // ── background removal — a COMMITTED step (like an eraser stroke), but
  // re-tunable in place while its panel is open. Opening it pushes a new
  // history entry computed from the pre-removal base; the sliders recompute
  // that same top entry from `bgBaseRef` so any later action keeps the result.
  const bgBaseRef = useRef<ImageData | null>(null);

  const renderBg = (t: number, s: number, rc: Recolor) => {
    const base = bgBaseRef.current;
    if (!base) return;
    const next = removeBackground(base, {
      threshold: t,
      softness: s,
      recolor: RECOLOR_HEX[rc],
    });
    setHistory((h) => {
      if (h.length === 0) return h;
      const c = [...h];
      c[c.length - 1] = next; // the bg step is always the top while tuning
      return c;
    });
  };

  const openBg = () => {
    if (!current) return;
    const base = current;
    bgBaseRef.current = base;
    const t = otsuThreshold(base);
    setThreshold(t);
    setSoftness(DEFAULT_SOFTNESS);
    setRecolor("keep");
    pushImage(
      removeBackground(base, {
        threshold: t,
        softness: DEFAULT_SOFTNESS,
        recolor: null,
      }),
    );
    setTool("bg");
  };
  const onBgThreshold = (v: number) => {
    setThreshold(v);
    renderBg(v, softness, recolor);
  };
  const onBgSoftness = (v: number) => {
    setSoftness(v);
    renderBg(threshold, v, recolor);
  };
  const onBgRecolor = (v: Recolor) => {
    setRecolor(v);
    renderBg(threshold, softness, v);
  };

  // ── pointer interactions (erase / crop) ──────────────────────────────────
  const toImage = (
    e: React.PointerEvent,
  ): { x: number; y: number; r: number } | null => {
    const el = overlayRef.current;
    if (!el || !current) return null;
    const rect = el.getBoundingClientRect();
    const sx = current.width / rect.width;
    const sy = current.height / rect.height;
    return {
      x: (e.clientX - rect.left) * sx,
      y: (e.clientY - rect.top) * sy,
      r: (brush / 2) * sx,
    };
  };
  const toDisplay = (
    e: React.PointerEvent,
  ): { x: number; y: number } | null => {
    const el = overlayRef.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || !current) return;
    const el = overlayRef.current;
    if (!el) return;
    if (tool === "erase") {
      el.setPointerCapture(e.pointerId);
      eraseRef.current = cloneImageData(current);
      drawingRef.current = true;
      const p = toImage(e);
      if (p) eraseCircleInPlace(eraseRef.current, p.x, p.y, p.r);
      bump();
    } else if (tool === "magic") {
      // One click = one committed erase of all matching pixels.
      const p = toImage(e);
      if (p)
        pushImage(magicErase(current, p.x, p.y, magicTol, magicContiguous));
    } else if (tool === "crop") {
      el.setPointerCapture(e.pointerId);
      const p = toDisplay(e);
      if (p) {
        cropStartRef.current = p;
        setCropRect({ x: p.x, y: p.y, w: 0, h: 0 });
      }
    } else if (tool === "none" && pannable) {
      // Hand tool: drag to pan the zoomed image around the stage.
      const sc = scrollRef.current;
      if (sc) {
        el.setPointerCapture(e.pointerId);
        panRef.current = {
          x: e.clientX,
          y: e.clientY,
          left: sc.scrollLeft,
          top: sc.scrollTop,
        };
        setIsPanning(true);
      }
    }
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (tool === "erase") {
      const d = toDisplay(e);
      if (d) setCursor(d);
      if (drawingRef.current && eraseRef.current) {
        const p = toImage(e);
        if (p) {
          eraseCircleInPlace(eraseRef.current, p.x, p.y, p.r);
          bump();
        }
      }
    } else if (tool === "crop" && cropStartRef.current) {
      const p = toDisplay(e);
      const start = cropStartRef.current;
      if (p)
        setCropRect({
          x: start.x,
          y: start.y,
          w: p.x - start.x,
          h: p.y - start.y,
        });
    } else if (panRef.current) {
      const sc = scrollRef.current;
      const start = panRef.current;
      if (sc) {
        sc.scrollLeft = start.left - (e.clientX - start.x);
        sc.scrollTop = start.top - (e.clientY - start.y);
      }
    }
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (tool === "erase" && drawingRef.current && eraseRef.current) {
      pushImage(eraseRef.current);
      eraseRef.current = null;
      drawingRef.current = false;
    } else if (tool === "crop") {
      cropStartRef.current = null;
    } else if (panRef.current) {
      panRef.current = null;
      setIsPanning(false);
    }
    overlayRef.current?.releasePointerCapture(e.pointerId);
  };

  const applyCrop = () => {
    const el = overlayRef.current;
    if (!el || !current || !cropRect) return;
    const rect = el.getBoundingClientRect();
    const sx = current.width / rect.width;
    const sy = current.height / rect.height;
    const r = normalizeRect(cropRect);
    if (r.w < 4 || r.h < 4) {
      setTool("none");
      setCropRect(null);
      return;
    }
    pushImage(cropImageData(current, r.x * sx, r.y * sy, r.w * sx, r.h * sy));
    setTool("none");
    setCropRect(null);
  };

  // ── inputs ───────────────────────────────────────────────────────────────
  const handlePasteButton = () => {
    void readClipboardImage().then((blob) => {
      if (blob) loadBlob(blob);
      else toast.info(t("editorModal.clipboardEmpty"));
    });
  };
  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) loadBlob(f);
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = imageFromDataTransfer(e.dataTransfer);
    if (f) loadBlob(f);
  };

  const handleConfirm = () => {
    if (!current) return;
    setBusy(true);
    imageDataToPngFile(current, baseName)
      .then((f) => {
        onConfirm(f);
      })
      .catch((e: unknown) => {
        setError(String(e));
        setBusy(false);
      });
  };

  const dispCrop = cropRect ? normalizeRect(cropRect) : null;

  return (
    <Modal
      isOpen
      onClose={onCancel}
      width={720}
      title={t("editorModal.title", { label: slotLabel })}
      description={t("editorModal.description")}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={onCancel}
            disabled={uploading || busy}
          >
            {t("editorModal.cancel")}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleConfirm}
            disabled={!hasImage || uploading || busy}
          >
            {uploading || busy ? <Spinner size="sm" /> : t("editorModal.save")}
          </button>
        </>
      }
    >
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={handleFile}
      />

      {error && (
        <div
          style={{ color: "var(--c-err)", fontSize: 12.5, marginBottom: 10 }}
        >
          {error}
        </div>
      )}

      {/* ── Stage ── */}
      <div
        ref={stageRef}
        onDragOver={(e) => {
          e.preventDefault();
        }}
        onDrop={onDrop}
        style={{
          position: "relative",
          height: PREVIEW_H,
          borderRadius: 8,
          border: "1px solid var(--border)",
          backgroundColor: "var(--bg-0)",
          backgroundImage:
            "linear-gradient(45deg, var(--bg-2) 25%, transparent 25%), linear-gradient(-45deg, var(--bg-2) 25%, transparent 25%), linear-gradient(45deg, transparent 75%, var(--bg-2) 75%), linear-gradient(-45deg, transparent 75%, var(--bg-2) 75%)",
          backgroundSize: "16px 16px",
          backgroundPosition: "0 0, 0 8px, 8px -8px, -8px 0",
          overflow: "hidden",
        }}
      >
        {!hasImage ? (
          <div
            className="flex flex-col items-center justify-center"
            style={{
              width: "100%",
              height: "100%",
              gap: 10,
              color: "var(--fg-2)",
              textAlign: "center",
              padding: PREVIEW_PAD,
              boxSizing: "border-box",
            }}
          >
            <ImagePlus size={26} style={{ color: "var(--fg-3)" }} />
            <div style={{ fontSize: 12.5 }}>{t("editorModal.dropPrompt")}</div>
            <div className="flex items-center" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn xs"
                onClick={() => fileRef.current?.click()}
              >
                <Upload size={11} />
                {t("editorModal.chooseFile")}
              </button>
              <button
                type="button"
                className="btn xs"
                onClick={handlePasteButton}
              >
                {t("editorModal.fromClipboard")}
              </button>
            </div>
          </div>
        ) : (
          <div
            ref={scrollRef}
            className="flex"
            style={{
              width: "100%",
              height: "100%",
              overflow: "auto",
              padding: PREVIEW_PAD,
              boxSizing: "border-box",
            }}
          >
            <div
              ref={overlayRef}
              style={{
                position: "relative",
                flex: "0 0 auto",
                margin: "auto",
                lineHeight: 0,
                touchAction: "none",
                cursor:
                  tool === "erase"
                    ? "none"
                    : tool === "crop" || tool === "magic"
                      ? "crosshair"
                      : pannable
                        ? isPanning
                          ? "grabbing"
                          : "grab"
                        : "default",
              }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={() => {
                setCursor(null);
              }}
            >
              <canvas ref={canvasRef} style={{ display: "block" }} />
              {/* crop selection */}
              {tool === "crop" && dispCrop && dispCrop.w > 0 && (
                <div
                  style={{
                    position: "absolute",
                    left: dispCrop.x,
                    top: dispCrop.y,
                    width: dispCrop.w,
                    height: dispCrop.h,
                    border: "1.5px dashed var(--accent)",
                    boxShadow:
                      "0 0 0 9999px color-mix(in oklch, var(--bg-0) 55%, transparent)",
                    pointerEvents: "none",
                  }}
                />
              )}
              {/* eraser cursor */}
              {tool === "erase" && cursor && (
                <div
                  style={{
                    position: "absolute",
                    left: cursor.x - brush / 2,
                    top: cursor.y - brush / 2,
                    width: brush,
                    height: brush,
                    borderRadius: "50%",
                    border: "1.5px solid var(--accent)",
                    background:
                      "color-mix(in oklch, var(--accent) 12%, transparent)",
                    pointerEvents: "none",
                  }}
                />
              )}
            </div>
          </div>
        )}

        {/* ── Zoom controls ── */}
        {hasImage && (
          <div
            className="flex items-center"
            style={{
              position: "absolute",
              right: 10,
              bottom: 10,
              zIndex: 2,
              gap: 2,
              padding: 3,
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--bg-1)",
              boxShadow:
                "0 2px 8px color-mix(in oklch, var(--bg-0) 55%, transparent)",
            }}
          >
            <button
              type="button"
              className="btn xs ghost"
              title={t("editorModal.zoomOutTitle")}
              onClick={() => {
                zoomFromCenter(zoom / ZOOM_STEP);
              }}
              disabled={zoom <= ZOOM_MIN + 0.001}
              style={{ padding: "3px 5px" }}
            >
              <ZoomOut size={13} />
            </button>
            <button
              type="button"
              className="btn xs ghost mono"
              title={t("editorModal.zoomResetTitle")}
              onClick={() => {
                zoomFromCenter(1);
              }}
              style={{ minWidth: 44, padding: "3px 4px" }}
            >
              {`${String(Math.round(zoom * 100))}%`}
            </button>
            <button
              type="button"
              className="btn xs ghost"
              title={t("editorModal.zoomInTitle")}
              onClick={() => {
                zoomFromCenter(zoom * ZOOM_STEP);
              }}
              disabled={zoom >= ZOOM_MAX - 0.001}
              style={{ padding: "3px 5px" }}
            >
              <ZoomIn size={13} />
            </button>
          </div>
        )}
      </div>

      {hasImage && (
        <>
          {/* ── Toolbar: row 1 = edit tools, row 2 = history + file ── */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              marginTop: 12,
            }}
          >
            <div
              className="flex items-center"
              style={{ gap: 6, flexWrap: "wrap" }}
            >
              <ToolBtn
                active={tool === "bg"}
                onClick={
                  tool === "bg"
                    ? () => {
                        setTool("none");
                      }
                    : openBg
                }
                icon={<Wand2 size={13} />}
                label={t("editorModal.removeBg")}
              />
              <ToolBtn
                active={tool === "erase"}
                onClick={() => {
                  setTool(tool === "erase" ? "none" : "erase");
                }}
                icon={<Eraser size={13} />}
                label={t("editorModal.eraser")}
              />
              <ToolBtn
                active={tool === "magic"}
                onClick={() => {
                  setTool(tool === "magic" ? "none" : "magic");
                }}
                icon={<Wand size={13} />}
                label={t("editorModal.magicEraser")}
              />
              <ToolBtn
                active={tool === "crop"}
                onClick={() => {
                  setTool(tool === "crop" ? "none" : "crop");
                }}
                icon={<Crop size={13} />}
                label={t("editorModal.crop")}
              />
              <button
                type="button"
                className="btn xs"
                onClick={applyAutoTrim}
                title={t("editorModal.autoTrimTitle")}
              >
                <Scissors size={12} />
                {t("editorModal.auto")}
              </button>
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  applyRotate("ccw");
                }}
                title={t("editorModal.rotateLeftTitle")}
              >
                <RotateCcw size={12} />
                {t("editorModal.degrees")}
              </button>
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  applyRotate("cw");
                }}
                title={t("editorModal.rotateRightTitle")}
              >
                <RotateCw size={12} />
                {t("editorModal.degrees")}
              </button>
            </div>

            <div
              className="flex items-center"
              style={{
                gap: 6,
                paddingTop: 8,
                borderTop: "1px solid var(--border)",
              }}
            >
              <button
                type="button"
                className="btn xs ghost"
                onClick={undo}
                disabled={!canUndo}
                title={t("editorModal.undoTitle")}
              >
                <Undo2 size={12} />
                {t("editorModal.undo")}
              </button>
              <button
                type="button"
                className="btn xs ghost"
                onClick={redo}
                disabled={!canRedo}
                title={t("editorModal.redoTitle")}
              >
                <Redo2 size={12} />
                {t("editorModal.redo")}
              </button>
              <button
                type="button"
                className="btn xs ghost"
                onClick={reset}
                title={t("editorModal.resetTitle")}
              >
                <RefreshCcw size={12} />
                {t("editorModal.reset")}
              </button>
              <button
                type="button"
                className="btn xs ghost"
                onClick={() => fileRef.current?.click()}
                title={t("editorModal.replaceTitle")}
                style={{ marginLeft: "auto" }}
              >
                <Upload size={12} />
                {t("editorModal.replace")}
              </button>
            </div>
          </div>

          {/* ── Tool sub-panels ── */}
          {tool === "bg" && (
            <ToolPanel>
              <div style={{ fontSize: 11, color: "var(--fg-2)" }}>
                {t("editorModal.bgHint")}
              </div>
              <SliderRow
                label={t("editorModal.bgThreshold")}
                value={threshold}
                min={1}
                max={254}
                onChange={onBgThreshold}
              />
              <SliderRow
                label={t("editorModal.bgSoftness")}
                value={softness}
                min={0}
                max={80}
                onChange={onBgSoftness}
              />
              <label
                className="flex items-center"
                style={{ gap: 8, fontSize: 11 }}
              >
                <span>{t("editorModal.inkColor")}</span>
                <select
                  value={recolor}
                  onChange={(e) => {
                    onBgRecolor(e.target.value as Recolor);
                  }}
                  style={selStyle}
                >
                  <option value="keep">{t("editorModal.inkKeep")}</option>
                  <option value="black">{t("editorModal.inkBlack")}</option>
                  <option value="blue">{t("editorModal.inkBlue")}</option>
                </select>
              </label>
              <div className="flex" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn xs"
                  onClick={() => {
                    setTool("none");
                  }}
                >
                  <XIcon size={11} />
                  {t("editorModal.done")}
                </button>
              </div>
            </ToolPanel>
          )}

          {tool === "erase" && (
            <ToolPanel>
              <SliderRow
                label={t("editorModal.brushSize")}
                value={brush}
                min={6}
                max={120}
                onChange={setBrush}
              />
              <div style={{ fontSize: 11, color: "var(--fg-2)" }}>
                {t("editorModal.eraseHint")}
              </div>
              <div className="flex" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn xs"
                  onClick={() => {
                    setTool("none");
                  }}
                >
                  <XIcon size={11} />
                  {t("editorModal.done")}
                </button>
              </div>
            </ToolPanel>
          )}

          {tool === "magic" && (
            <ToolPanel>
              <div style={{ fontSize: 11, color: "var(--fg-2)" }}>
                {t("editorModal.magicHint")}
              </div>
              <SliderRow
                label={t("editorModal.magicTolerance")}
                value={magicTol}
                min={0}
                max={150}
                onChange={setMagicTol}
              />
              <label
                className="flex items-center"
                style={{ gap: 8, fontSize: 11 }}
              >
                <span>{t("editorModal.magicArea")}</span>
                <select
                  value={magicContiguous ? "near" : "all"}
                  onChange={(e) => {
                    setMagicContiguous(e.target.value === "near");
                  }}
                  style={selStyle}
                >
                  <option value="near">{t("editorModal.magicAreaNear")}</option>
                  <option value="all">{t("editorModal.magicAreaAll")}</option>
                </select>
              </label>
              <div className="flex" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn xs"
                  onClick={() => {
                    setTool("none");
                  }}
                >
                  <XIcon size={11} />
                  {t("editorModal.done")}
                </button>
              </div>
            </ToolPanel>
          )}

          {tool === "crop" && (
            <ToolPanel>
              <div style={{ fontSize: 11, color: "var(--fg-2)" }}>
                {t("editorModal.cropHint")}
              </div>
              <PanelActions
                onApply={applyCrop}
                applyLabel={t("editorModal.cropApply")}
                applyDisabled={!dispCrop || dispCrop.w < 4}
                onCancel={() => {
                  setTool("none");
                  setCropRect(null);
                }}
              />
            </ToolPanel>
          )}
        </>
      )}
    </Modal>
  );
};

// ── small presentational helpers ───────────────────────────────────────────

const selStyle: React.CSSProperties = {
  fontSize: 11,
  background: "var(--bg-2)",
  border: "1px solid var(--border)",
  borderRadius: 4,
  padding: "2px 6px",
  color: "var(--fg-0)",
};

type ToolBtnProps = {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
};
const ToolBtn = ({ active, onClick, icon, label }: ToolBtnProps) => (
  <button
    type="button"
    className={active ? "btn xs btn-primary" : "btn xs"}
    onClick={onClick}
  >
    {icon}
    {label}
  </button>
);

const ToolPanel = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: 12,
      marginTop: 12,
      padding: "12px 14px",
      borderRadius: 8,
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
    }}
  >
    {children}
  </div>
);

type SliderRowProps = {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
};
const SliderRow = ({ label, value, min, max, onChange }: SliderRowProps) => (
  <label
    style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}
  >
    <span className="flex items-center justify-between">
      <span>{label}</span>
      <span className="mono dim">{value}</span>
    </span>
    <input
      type="range"
      min={min}
      max={max}
      value={value}
      onChange={(e) => {
        onChange(Number(e.target.value));
      }}
    />
  </label>
);

type PanelActionsProps = {
  onApply: () => void;
  onCancel: () => void;
  applyLabel?: string;
  applyDisabled?: boolean;
};
const PanelActions = ({
  onApply,
  onCancel,
  applyLabel,
  applyDisabled,
}: PanelActionsProps) => {
  const { t } = useTranslation("signatureStamper");
  return (
    <div
      className="flex items-center"
      style={{ gap: 8, justifyContent: "flex-end" }}
    >
      <button type="button" className="btn xs ghost" onClick={onCancel}>
        {t("editorModal.panelCancel")}
      </button>
      <button
        type="button"
        className="btn xs btn-primary"
        onClick={onApply}
        disabled={applyDisabled}
      >
        {applyLabel ?? t("editorModal.panelApply")}
      </button>
    </div>
  );
};
