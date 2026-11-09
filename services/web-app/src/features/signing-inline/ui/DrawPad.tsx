import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Eraser } from "lucide-react";
import { Button } from "@shared/ui";
import {
  INK_WIDTH,
  paintStrokes,
  strokesToPng,
  type Stroke,
} from "../lib/strokes";

export type DrawPadProps = {
  busy: boolean;
  onCancel: () => void;
  /** Готовая подпись: PNG без фона, обрезанный по чернилам (ещё растрируется). */
  onDone: (png: Promise<Blob>) => void;
};

/**
 * Подпись пальцем или мышью (docs/design/signing-route.md, 6.10). Лист всегда белый: так
 * подпись выглядит как на бумаге в любой теме. Жесты страницы на листе отключены.
 */
export const DrawPad = ({ busy, onCancel, onDone }: DrawPadProps) => {
  const { t } = useTranslation("signing");
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const strokes = useRef<Stroke[]>([]);
  const drawing = useRef(false);
  const [empty, setEmpty] = useState(true);

  const repaint = useCallback(() => {
    const canvas = canvasRef.current;
    const g = canvas?.getContext("2d");
    if (!canvas || !g) return;
    const ratio = window.devicePixelRatio || 1;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, canvas.width, canvas.height);
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    paintStrokes(g, strokes.current, INK_WIDTH);
  }, []);

  // Холст под плотность экрана; при повороте телефона и смене ширины подгоняется заново.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const fit = () => {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(canvas.clientWidth * ratio);
      canvas.height = Math.round(canvas.clientHeight * ratio);
      repaint();
    };
    fit();
    window.addEventListener("resize", fit);
    return () => {
      window.removeEventListener("resize", fit);
    };
  }, [repaint]);

  const pointOf = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  };

  return (
    <div className="sgi-draw" data-testid="signing-draw">
      <p className="sgi-hint">{t("image.drawHint")}</p>
      <canvas
        ref={canvasRef}
        className="sgi-canvas"
        aria-label={t("image.drawHint")}
        data-testid="signing-draw-canvas"
        onPointerDown={(event) => {
          if (busy) return;
          // jsdom и старые браузеры: захват указателя необязателен.
          (
            event.currentTarget as Partial<HTMLCanvasElement>
          ).setPointerCapture?.(event.pointerId);
          drawing.current = true;
          strokes.current.push([pointOf(event)]);
          setEmpty(false);
          repaint();
        }}
        onPointerMove={(event) => {
          if (!drawing.current) return;
          strokes.current.at(-1)?.push(pointOf(event));
          repaint();
        }}
        onPointerUp={() => {
          drawing.current = false;
        }}
        onPointerCancel={() => {
          drawing.current = false;
        }}
      />
      <div className="sgi-row">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={empty || busy}
          onClick={() => {
            strokes.current = [];
            setEmpty(true);
            repaint();
          }}
          data-testid="signing-draw-clear"
        >
          <Eraser size="0.8125rem" aria-hidden />
          {t("image.clear")}
        </Button>
        <span className="sgi-grow" />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy}
          onClick={onCancel}
        >
          {t("image.cancel")}
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={empty || busy}
          onClick={() => {
            onDone(strokesToPng(strokes.current));
          }}
          data-testid="signing-draw-done"
        >
          {t("image.done")}
        </Button>
      </div>
    </div>
  );
};
