import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import {
  placePopover,
  spotlightRect,
  type PopoverBox,
  type Rect,
} from "./placement";
import { useTargetRect } from "./useTargetRect";

export type TourOverlayLabels = {
  next: string;
  back: string;
  skip: string;
  finish: string;
  /** «Шаг 3 из 9». */
  progress: string;
  close: string;
};

export type TourOverlayProps = {
  /** Ключ шага: при его смене фокус уходит на главную кнопку подсказки. */
  stepId: string;
  /** CSS-селектор подсвечиваемого элемента. Нет или не найден — подсказка по центру. */
  target?: string | undefined;
  title: ReactNode;
  body: ReactNode;
  /** Метка над заголовком (например, «Демо»). */
  badge?: ReactNode | undefined;
  index: number;
  total: number;
  labels: TourOverlayLabels;
  onNext: () => void;
  onBack?: (() => void) | undefined;
  onSkip: () => void;
  /** Подпись главной кнопки вместо «Далее» (например, «Собрать»). */
  primaryLabel?: string | undefined;
  primaryBusy?: boolean | undefined;
  /** Пропускать клики к подсвеченному элементу (шаги, где человек делает действие сам). */
  interactive?: boolean | undefined;
};

const isTyping = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
};

const reducedMotion = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const DIM = "rgba(0, 0, 0, 0.56)";

/** Четыре затемняющие полосы вокруг «окна»: клики мимо элемента не доходят до страницы. */
const Blockers = ({
  spot,
  dim,
  interactive,
}: {
  spot: Rect | null;
  dim: boolean;
  interactive: boolean;
}) => {
  const base: CSSProperties = {
    position: "fixed",
    background: dim ? DIM : "transparent",
    pointerEvents: "auto",
  };
  if (!spot) {
    return <div style={{ ...base, inset: 0 }} data-tour-blocker="" />;
  }
  const { top, left, width, height } = spot;
  return (
    <>
      <div style={{ ...base, top: 0, left: 0, right: 0, height: top }} />
      <div
        style={{ ...base, top: top + height, left: 0, right: 0, bottom: 0 }}
      />
      <div style={{ ...base, top, left: 0, width: left, height }} />
      <div style={{ ...base, top, left: left + width, right: 0, height }} />
      {!interactive && (
        <div
          style={{ position: "fixed", top, left, width, height }}
          aria-hidden="true"
        />
      )}
    </>
  );
};

/**
 * Шаг тура: затемнение с окном вокруг элемента и подсказка рядом.
 * Клавиатура: → и Enter вперёд, ← назад, Esc пропустить тур.
 */
export const TourOverlay = ({
  stepId,
  target,
  title,
  body,
  badge,
  index,
  total,
  labels,
  onNext,
  onBack,
  onSkip,
  primaryLabel,
  primaryBusy = false,
  interactive = false,
}: TourOverlayProps) => {
  const { rect, viewport } = useTargetRect(target);
  const spot = useMemo(
    () => (rect ? spotlightRect(rect, viewport) : null),
    [rect, viewport],
  );
  const boxRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const [box, setBox] = useState<PopoverBox>({
    top: -9999,
    left: -9999,
    placement: "center",
  });
  const isLast = index === total - 1;
  const animate = !reducedMotion();

  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const size = { width: el.offsetWidth, height: el.offsetHeight };
    const next = placePopover(spot, size, viewport);
    setBox((prev) =>
      prev.top === next.top &&
      prev.left === next.left &&
      prev.placement === next.placement
        ? prev
        : next,
    );
  }, [spot, viewport, stepId, title, body]);

  useEffect(() => {
    primaryRef.current?.focus({ preventScroll: true });
  }, [stepId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onSkip();
        return;
      }
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        if (!primaryBusy) onNext();
      } else if (e.key === "ArrowLeft" && onBack) {
        e.preventDefault();
        onBack();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [onNext, onBack, onSkip, primaryBusy]);

  const sheet = box.placement === "sheet";
  const width = sheet
    ? viewport.width - 24
    : Math.min(380, viewport.width - 24);

  return createPortal(
    <div
      data-testid="tour-overlay"
      data-tour-step={stepId}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 150,
        pointerEvents: "none",
      }}
    >
      <Blockers spot={spot} dim={!spot} interactive={interactive} />
      {spot && (
        <div
          aria-hidden="true"
          data-testid="tour-spotlight"
          style={{
            position: "fixed",
            top: spot.top,
            left: spot.left,
            width: spot.width,
            height: spot.height,
            borderRadius: "var(--r-3)",
            boxShadow: `0 0 0 9999px ${DIM}, 0 0 0 2px var(--accent)`,
            pointerEvents: "none",
            transition: animate
              ? "top .2s ease, left .2s ease, width .2s ease, height .2s ease"
              : undefined,
          }}
        />
      )}
      <div
        ref={boxRef}
        role="dialog"
        aria-modal="false"
        aria-labelledby={`tour-title-${stepId}`}
        aria-describedby={`tour-body-${stepId}`}
        data-testid="tour-popover"
        data-placement={box.placement}
        style={{
          position: "fixed",
          top: box.top,
          left: box.left,
          width,
          pointerEvents: "auto",
          background: "var(--bg-1)",
          color: "var(--fg-0)",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-4)",
          boxShadow: "var(--shadow-pop)",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          transition: animate ? "top .2s ease, left .2s ease" : undefined,
        }}
      >
        <div className="flex items-center justify-between" style={{ gap: 8 }}>
          <span
            className="mono dim"
            aria-live="polite"
            style={{ fontSize: 10.5, letterSpacing: "0.08em" }}
          >
            {badge}
            {badge ? " · " : ""}
            {labels.progress}
          </span>
          <button
            type="button"
            className="icon-btn"
            aria-label={labels.close}
            onClick={onSkip}
            style={{ width: 24, height: 24 }}
          >
            <X size={13} />
          </button>
        </div>
        <div
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={total}
          aria-valuenow={index + 1}
          aria-label={labels.progress}
          style={{
            height: 3,
            borderRadius: 2,
            background: "var(--bg-3)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${String(((index + 1) / total) * 100)}%`,
              height: "100%",
              background: "var(--accent)",
            }}
          />
        </div>
        <h2
          id={`tour-title-${stepId}`}
          style={{ margin: 0, fontSize: 15, fontWeight: 600 }}
        >
          {title}
        </h2>
        <div
          id={`tour-body-${stepId}`}
          style={{ fontSize: 13, lineHeight: 1.5, color: "var(--fg-1)" }}
        >
          {body}
        </div>
        <div
          className="flex items-center justify-between"
          style={{ gap: 8, marginTop: 4, flexWrap: "wrap" }}
        >
          <button
            type="button"
            className="btn ghost sm"
            onClick={onSkip}
            data-testid="tour-skip"
          >
            {labels.skip}
          </button>
          <div className="flex items-center" style={{ gap: 6 }}>
            {onBack && index > 0 && (
              <button
                type="button"
                className="btn sm"
                onClick={onBack}
                data-testid="tour-back"
              >
                {labels.back}
              </button>
            )}
            <button
              ref={primaryRef}
              type="button"
              className="btn primary sm"
              onClick={onNext}
              disabled={primaryBusy}
              aria-busy={primaryBusy}
              data-testid="tour-next"
            >
              {primaryLabel ?? (isLast ? labels.finish : labels.next)}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};
