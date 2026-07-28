import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type * as pdfjsLib from "pdfjs-dist";
import type { PageDim } from "./PdfPage";

const THUMB_WIDTH = 132;

type PdfThumbnailsProps = {
  pdf: pdfjsLib.PDFDocumentProxy;
  pages: PageDim[];
  currentPage: number;
  onJump: (pageNum: number) => void;
};

export const PdfThumbnails = ({
  pdf,
  pages,
  currentPage,
  onJump,
}: PdfThumbnailsProps) => {
  return (
    <div className="pdf-thumbs">
      {pages.map((dim) => (
        <Thumb
          key={dim.num}
          pdf={pdf}
          dim={dim}
          active={dim.num === currentPage}
          onJump={onJump}
        />
      ))}
    </div>
  );
};

const Thumb = ({
  pdf,
  dim,
  active,
  onJump,
}: {
  pdf: pdfjsLib.PDFDocumentProxy;
  dim: PageDim;
  active: boolean;
  onJump: (pageNum: number) => void;
}) => {
  const { t } = useTranslation("pdfViewer");
  const wrapRef = useRef<HTMLButtonElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const scale = THUMB_WIDTH / dim.widthPt;
  const heightPx = dim.heightPt * scale;

  // Keep the active thumbnail in view as the user scrolls the main page list.
  useEffect(() => {
    if (active) wrapRef.current?.scrollIntoView({ block: "nearest" });
  }, [active]);

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
      { rootMargin: "600px" },
    );
    io.observe(el);
    return () => {
      io.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!visible) return;
    const ctl = {
      cancelled: false,
      render: undefined as pdfjsLib.RenderTask | undefined,
    };
    void (async () => {
      const page = await pdf.getPage(dim.num);
      if (ctl.cancelled) return;
      const dpr = window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: scale * dpr });
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      if (!canvas || !ctx) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      ctl.render = page.render({ canvasContext: ctx, viewport, canvas });
      await ctl.render.promise.catch(() => undefined);
    })().catch(() => undefined);
    return () => {
      ctl.cancelled = true;
      ctl.render?.cancel();
    };
  }, [visible, pdf, dim.num, scale]);

  return (
    <button
      ref={wrapRef}
      type="button"
      className={active ? "pdf-thumb active" : "pdf-thumb"}
      onClick={() => {
        onJump(dim.num);
      }}
      title={t("thumb.pageTitle", { n: dim.num })}
    >
      <canvas
        ref={canvasRef}
        style={{ width: THUMB_WIDTH, height: heightPx }}
      />
      <span className="pdf-thumb-num mono">{dim.num}</span>
    </button>
  );
};
