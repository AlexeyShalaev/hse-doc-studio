import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
// Vite resolves this to a hashed asset URL pointing at the worker bundle. Using
// `?url` keeps the worker out of the main JS chunk while still letting
// pdfjs-dist find it at runtime via GlobalWorkerOptions.workerSrc.
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

// Configure once. Calling this every render would be harmless (it's a static
// global), but keeping it at module scope avoids subtle race conditions where
// a later render might overwrite the worker URL while a job is in flight.
pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

type UsePdfPageResult = {
  isLoading: boolean;
  isError: boolean;
  pageCount: number;
  // Page size in PDF native units (points). The caller converts these into a
  // responsive on-screen size (mm-space ⇄ px-space) at whatever display scale
  // fits the current pane width.
  pageWidthPt: number;
  pageHeightPt: number;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
};

// How many raster pixels we draw per PDF point. Fixed and generous so the page
// stays crisp; the *on-screen* size is chosen responsively by the caller, which
// CSS-scales this raster down to fit the pane (never up past it) — and
// downscaling a raster always stays sharp.
const RENDER_SCALE = 2;

export const usePdfPage = (
  pdfUrl: string | null,
  pageNumber: number,
): UsePdfPageResult => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);
  const [pageCount, setPageCount] = useState(0);
  const [pageWidthPt, setPageWidthPt] = useState(0);
  const [pageHeightPt, setPageHeightPt] = useState(0);

  useEffect(() => {
    if (!pdfUrl) return;
    let cancelled = false;
    let loadingTask: ReturnType<typeof pdfjsLib.getDocument> | null = null;

    const render = async () => {
      setIsLoading(true);
      setIsError(false);
      try {
        loadingTask = pdfjsLib.getDocument({
          url: pdfUrl,
          withCredentials: true,
        });
        const pdf = await loadingTask.promise;
        if (cancelled) return;
        setPageCount(pdf.numPages);
        const target = Math.min(Math.max(1, pageNumber), pdf.numPages);
        const page = await pdf.getPage(target);
        if (cancelled) return;
        const viewport = page.getViewport({ scale: RENDER_SCALE });
        const canvas = canvasRef.current;
        if (!canvas) return;
        // Only the raster (attribute) size is set here; the displayed CSS size
        // is owned by the caller so it can shrink the page to fit the pane.
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        await page.render({ canvasContext: ctx, viewport, canvas }).promise;
        if (cancelled) return;
        setPageWidthPt(viewport.width / RENDER_SCALE);
        setPageHeightPt(viewport.height / RENDER_SCALE);
        setIsLoading(false);
      } catch (err) {
        if (cancelled) return;
        const isAbort =
          err instanceof Error &&
          (err.name === "RenderingCancelledException" ||
            err.message.includes("cancelled"));
        if (!isAbort) {
          setIsError(true);
          setIsLoading(false);
        }
      }
    };

    void render();

    return () => {
      cancelled = true;
      if (loadingTask) {
        void loadingTask.destroy();
      }
    };
  }, [pdfUrl, pageNumber]);

  // No URL → nothing to load. Surface that as a stable, non-loading empty
  // result rather than syncing it from inside the effect, which the React
  // hooks lint rule (rightfully) flags as a cascading render.
  if (!pdfUrl) {
    return {
      isLoading: false,
      isError: false,
      pageCount: 0,
      pageWidthPt: 0,
      pageHeightPt: 0,
      canvasRef,
    };
  }

  return {
    isLoading,
    isError,
    pageCount,
    pageWidthPt,
    pageHeightPt,
    canvasRef,
  };
};
