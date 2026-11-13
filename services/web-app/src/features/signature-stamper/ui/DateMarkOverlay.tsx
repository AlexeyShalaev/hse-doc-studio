import { useEffect, useRef, useState } from "react";
import type { DateMarkAlign } from "@shared/api/types";
import { dateMarkFontPt } from "@entities/signature";
import type { DateMarkPlace } from "../lib/dateMarkEdit";

// Рамка метки даты на превью страницы (docs/design/signing-route.md, 14.2): пунктир своего цвета,
// чтобы не спутать с подписью. Её двигают и тянут за угол, как рамку подписи, но ширина и высота
// меняются независимо: метка это строка текста, а не картинка. Внутри то, что напечатается
// (или пример по сегодняшней дате), кеглем, который подберёт сервер.

/** Цвет меток даты: отличается от акцента рамок подписи в любой теме. */
export const DATE_MARK_COLOR = "var(--chart-4)";

const MIN_WIDTH_MM = 4;
const MIN_HEIGHT_MM = 3;
const MIN_FONT_PT = 6;
const PT_PER_MM = 72 / 25.4;

export type DateMarkOverlayProps = {
  place: DateMarkPlace;
  /** Что напечатается в рамке (или пример). */
  text: string;
  align: DateMarkAlign;
  /** Подпись рамки: «Дата: 13». */
  label: string;
  pageWidthMm: number;
  pageHeightMm: number;
  pxPerMm: number;
  /** Рамку можно двигать (у документа под маршрутом тоже, 14.6). */
  editable: boolean;
  testId?: string;
  /** Отпускание указателя после перетаскивания или растягивания. */
  onCommit: (next: DateMarkPlace) => void;
};

type Gesture =
  | { kind: "idle" }
  | {
      kind: "drag" | "resize";
      pointerId: number;
      startX: number;
      startY: number;
      base: DateMarkPlace;
    };

const clamp = (value: number, min: number, max: number): number =>
  Math.min(Math.max(value, min), Math.max(min, max));

export const DateMarkOverlay = ({
  place,
  text,
  align,
  label,
  pageWidthMm,
  pageHeightMm,
  pxPerMm,
  editable,
  testId,
  onCommit,
}: DateMarkOverlayProps) => {
  // Как у рамки подписи: во время жеста рамка живёт своим состоянием, наверх уходит только итог.
  const [local, setLocal] = useState(place);
  const [active, setActive] = useState(false);
  const [hover, setHover] = useState(false);
  const gesture = useRef<Gesture>({ kind: "idle" });
  const { x_mm, y_mm, width_mm, height_mm } = place;
  useEffect(() => {
    if (gesture.current.kind === "idle")
      setLocal({ x_mm, y_mm, width_mm, height_mm });
  }, [x_mm, y_mm, width_mm, height_mm]);

  const begin = (
    kind: "drag" | "resize",
    e: React.PointerEvent<HTMLDivElement>,
    host: Element | null,
  ) => {
    if (!editable || e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    host?.setPointerCapture(e.pointerId);
    gesture.current = {
      kind,
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      base: local,
    };
    setActive(true);
  };

  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = gesture.current;
    if (g.kind === "idle" || g.pointerId !== e.pointerId) return;
    const dx = (e.clientX - g.startX) / pxPerMm;
    const dy = (e.clientY - g.startY) / pxPerMm;
    if (g.kind === "drag") {
      setLocal({
        ...g.base,
        x_mm: clamp(g.base.x_mm + dx, 0, pageWidthMm - g.base.width_mm),
        y_mm: clamp(g.base.y_mm + dy, 0, pageHeightMm - g.base.height_mm),
      });
    } else {
      setLocal({
        ...g.base,
        width_mm: clamp(
          g.base.width_mm + dx,
          MIN_WIDTH_MM,
          pageWidthMm - g.base.x_mm,
        ),
        height_mm: clamp(
          g.base.height_mm + dy,
          MIN_HEIGHT_MM,
          pageHeightMm - g.base.y_mm,
        ),
      });
    }
  };

  const finish = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = gesture.current;
    if (g.kind === "idle" || g.pointerId !== e.pointerId) return;
    e.currentTarget.releasePointerCapture(e.pointerId);
    gesture.current = { kind: "idle" };
    setActive(false);
    const moved =
      local.x_mm !== g.base.x_mm ||
      local.y_mm !== g.base.y_mm ||
      local.width_mm !== g.base.width_mm ||
      local.height_mm !== g.base.height_mm;
    if (moved) onCommit(local);
  };

  // Пиксели на пункт PDF: кегль сервера переводится в размер на экране.
  const pxPerPt = pxPerMm / PT_PER_MM;
  const fontPx =
    Math.max(
      MIN_FONT_PT,
      dateMarkFontPt(text, local.width_mm, local.height_mm),
    ) * pxPerPt;

  return (
    <div
      data-testid={testId}
      role="img"
      aria-label={label}
      title={label}
      onPointerDown={(e) => {
        begin("drag", e, e.currentTarget);
      }}
      onPointerMove={move}
      onPointerUp={finish}
      onPointerCancel={finish}
      onPointerEnter={() => {
        setHover(true);
      }}
      onPointerLeave={() => {
        setHover(false);
      }}
      style={{
        position: "absolute",
        left: local.x_mm * pxPerMm,
        top: local.y_mm * pxPerMm,
        width: local.width_mm * pxPerMm,
        height: local.height_mm * pxPerMm,
        boxSizing: "border-box",
        border: `1.5px dashed ${DATE_MARK_COLOR}`,
        background: `color-mix(in oklch, ${DATE_MARK_COLOR} 10%, transparent)`,
        display: "flex",
        alignItems: "center",
        justifyContent:
          align === "left"
            ? "flex-start"
            : align === "right"
              ? "flex-end"
              : "center",
        padding: "0 1px",
        cursor: editable ? (active ? "grabbing" : "grab") : "default",
        touchAction: "none",
        // Документ на подписании: рамки подписей не слушают указатель, метки даты слушают.
        pointerEvents: editable ? "auto" : "none",
      }}
    >
      <span
        style={{
          fontSize: fontPx,
          lineHeight: 1,
          whiteSpace: "nowrap",
          overflow: "hidden",
          color: "#000",
          opacity: 0.6,
          pointerEvents: "none",
          userSelect: "none",
        }}
      >
        {text}
      </span>
      {(hover || active) && (
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            left: -1.5,
            bottom: "100%",
            padding: "0 0.3125rem",
            borderRadius: "0.1875rem 0.1875rem 0 0",
            background: DATE_MARK_COLOR,
            color: "#fff",
            fontSize: "0.625rem",
            lineHeight: 1.5,
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
        >
          {label}
        </span>
      )}
      {editable && (
        <div
          onPointerDown={(e) => {
            begin("resize", e, e.currentTarget.parentElement);
          }}
          style={{
            position: "absolute",
            right: "-0.375rem",
            bottom: "-0.375rem",
            width: "0.75rem",
            height: "0.75rem",
            background: DATE_MARK_COLOR,
            border: "2px solid var(--bg-0)",
            borderRadius: "0.1875rem",
            cursor: "nwse-resize",
            touchAction: "none",
          }}
        />
      )}
    </div>
  );
};
