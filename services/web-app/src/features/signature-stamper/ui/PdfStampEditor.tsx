import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, FileWarning } from "lucide-react";
import type {
  PlacementResponse,
  SignaturesStateResponse,
  SignatureSlotDefResponse,
  SlotInfoResponse,
} from "@shared/api/types";
import { env } from "@shared/config";
import { pickLocalized } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { aspectRatioFromPx, MM_PER_PT, PT_PER_MM } from "../lib/coords";
import { usePdfPage } from "../lib/usePdfPage";
import { SignatureOverlay } from "./SignatureOverlay";

export type PdfStampEditorProps = {
  projectId: string;
  docId: string;
  pdfRelPath: string;
  pdfAvailable: boolean;
  slotDefs: readonly SignatureSlotDefResponse[];
  state: SignaturesStateResponse;
  // Controlled page state so callers can sync the preview page with
  // sidebar UI (e.g. "place this signature on the page I'm currently
  // looking at"). Cb fires on prev/next/typed-input.
  page: number;
  onPageChange: (page: number) => void;
  onPageCountChange?: (count: number) => void;
  onPlacementChange: (
    slotId: string,
    patch: {
      x_mm?: number;
      y_mm?: number;
      width_mm?: number;
      page?: number;
      enabled?: boolean;
    },
  ) => void;
  onCompileRequest?: () => void;
  isCompileRunning?: boolean;
};

// The horizontal padding (px, each side) of the scrollable preview area. We
// strip it off the measured width so the page is fit to the *content* box.
const PREVIEW_PADDING = 16;
// Largest on-screen scale (CSS px per PDF point). At full width the page shows
// at this "100%" size; a narrower pane scales it down to fit instead of
// clipping it behind whatever sits to the right (e.g. the docked agent chat).
const MAX_DISPLAY_SCALE = 1.5;
// Floor so an extremely narrow pane still shows a (tiny) page rather than
// collapsing it to nothing.
const MIN_DISPLAY_SCALE = 0.15;

const buildPngUrl = (projectId: string, pngPath: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${pngPath}`;

const buildPdfUrl = (projectId: string, pdfRelPath: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${pdfRelPath}`;

export const PdfStampEditor = ({
  projectId,
  docId,
  pdfRelPath,
  pdfAvailable,
  slotDefs,
  state,
  page,
  onPageChange,
  onPageCountChange,
  onPlacementChange,
  onCompileRequest,
  isCompileRunning,
}: PdfStampEditorProps) => {
  const { t, i18n } = useTranslation("signatureStamper");
  const pdfUrl = pdfAvailable ? buildPdfUrl(projectId, pdfRelPath) : null;
  const {
    isLoading,
    isError,
    pageCount,
    pageWidthPt,
    pageHeightPt,
    canvasRef,
  } = usePdfPage(pdfUrl, page);

  useEffect(() => {
    onPageCountChange?.(pageCount);
  }, [pageCount, onPageCountChange]);

  // Track the available preview width so the page can shrink to fit it. Without
  // this the canvas keeps its fixed render size and gets clipped behind the
  // panel docked to its right (the agent chat) instead of narrowing with it.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [availWidth, setAvailWidth] = useState(0);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // clientWidth excludes the (gutter-reserved) scrollbar; strip the padding
    // so we fit the content box, and a stable gutter keeps it from oscillating.
    const measure = () => {
      setAvailWidth(Math.max(0, el.clientWidth - PREVIEW_PADDING * 2));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
    // Re-attach when the preview first appears: the scroll container is only
    // mounted once a build exists, so a bare [] would miss the not-compiled →
    // compiled transition and leave the page unmeasured (stuck at full size).
  }, [pdfAvailable]);

  // Fit-to-width, capped at the natural "100%" size and never below the floor.
  // Until the page (and pane) are measured, fall back to the natural scale.
  const fitScale =
    pageWidthPt > 0 && availWidth > 0 ? availWidth / pageWidthPt : null;
  const displayScale =
    fitScale === null
      ? MAX_DISPLAY_SCALE
      : Math.max(MIN_DISPLAY_SCALE, Math.min(MAX_DISPLAY_SCALE, fitScale));

  const pageWidthMm = pageWidthPt * MM_PER_PT;
  const pageHeightMm = pageHeightPt * MM_PER_PT;
  const pxPerMm = displayScale * PT_PER_MM;
  const displayWidthPx = pageWidthPt * displayScale;
  const displayHeightPx = pageHeightPt * displayScale;

  // The page input is uncontrolled with a key bound to `page` — when the
  // page changes from outside (prev/next click, "Перейти" in sidebar), React
  // remounts the input and it shows the new value. While the user is
  // typing, the input drives itself; commit on blur or Enter, clamped to
  // [1, pageCount].
  const commitPageInput = (raw: string) => {
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || pageCount === 0) return;
    const clamped = Math.min(pageCount, Math.max(1, Math.round(parsed)));
    if (clamped !== page) onPageChange(clamped);
  };

  const overlays = useMemo(() => {
    return slotDefs
      .filter((slot) => slot.applies_to.includes(docId))
      .map((slot) => {
        const placement: PlacementResponse | undefined =
          state.placements[docId]?.[slot.id];
        const slotInfo: SlotInfoResponse | undefined = state.slots[slot.id];
        return { slot, placement, slotInfo };
      })
      .filter(
        (entry) => entry.placement?.enabled && entry.placement?.page === page,
      );
  }, [slotDefs, docId, state, page]);

  if (!pdfAvailable) {
    return (
      <div
        className="flex flex-col items-center justify-center"
        style={{ flex: 1, padding: 40, gap: 16, minHeight: 0 }}
      >
        <FileWarning size={28} style={{ color: "var(--c-warn)" }} />
        <p
          className="dim"
          style={{ margin: 0, textAlign: "center", maxWidth: 380 }}
        >
          <Trans
            i18nKey="pdfEditor.notCompiled"
            ns="signatureStamper"
            values={{ docId }}
            components={[<code className="mono" key="doc" />]}
          />
        </p>
        {onCompileRequest && (
          <button
            type="button"
            className="btn"
            onClick={onCompileRequest}
            disabled={isCompileRunning}
          >
            {isCompileRunning ? t("pdfEditor.building") : t("pdfEditor.build")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      <div
        className="flex items-center"
        style={{
          padding: "8px 14px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
          gap: 10,
          fontSize: 11.5,
        }}
      >
        <span className="mono dim" style={{ fontSize: 10 }}>
          {pdfRelPath}
        </span>
        <div
          className="flex items-center"
          style={{ gap: 6, marginLeft: "auto" }}
        >
          <button
            type="button"
            className="btn xs"
            disabled={page <= 1 || isLoading}
            onClick={() => {
              onPageChange(Math.max(1, page - 1));
            }}
            aria-label={t("pdfEditor.prevPage")}
          >
            <ChevronLeft size={11} />
          </button>
          <div className="flex items-center" style={{ gap: 4, fontSize: 11 }}>
            <span className="dim">{t("pdfEditor.pageShort")}</span>
            <input
              key={page}
              type="number"
              min={1}
              max={pageCount || undefined}
              defaultValue={page}
              disabled={isLoading || pageCount === 0}
              onBlur={(e) => {
                commitPageInput(e.target.value);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.currentTarget.blur();
                }
              }}
              className="input mono"
              style={{
                width: 52,
                height: 22,
                fontSize: 11,
                textAlign: "center",
                padding: "0 4px",
              }}
              aria-label={t("pdfEditor.pageNumberAria")}
            />
            <span className="dim mono">/ {pageCount || "?"}</span>
          </div>
          <button
            type="button"
            className="btn xs"
            disabled={page >= pageCount || isLoading}
            onClick={() => {
              onPageChange(Math.min(pageCount, page + 1));
            }}
            aria-label={t("pdfEditor.nextPage")}
          >
            <ChevronRight size={11} />
          </button>
        </div>
      </div>
      <div
        ref={scrollRef}
        className="flex justify-center"
        style={{
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          overflow: "auto",
          scrollbarGutter: "stable",
          padding: PREVIEW_PADDING,
          background: "var(--bg-0)",
        }}
      >
        {isError ? (
          <div className="dim" style={{ padding: 40 }}>
            {t("pdfEditor.loadFailed")}
          </div>
        ) : (
          <div
            style={{
              position: "relative",
              lineHeight: 0,
              flexShrink: 0,
              width: displayWidthPx || undefined,
              height: displayHeightPx || undefined,
            }}
          >
            <canvas
              ref={canvasRef}
              style={{
                display: "block",
                width: displayWidthPx || undefined,
                height: displayHeightPx || undefined,
                boxShadow:
                  "0 4px 24px color-mix(in oklch, var(--fg-0) 12%, transparent)",
                background: "white",
              }}
            />
            {isLoading && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background:
                    "color-mix(in oklch, var(--bg-0) 80%, transparent)",
                }}
              >
                <Spinner />
              </div>
            )}
            {!isLoading &&
              overlays.map(({ slot, placement, slotInfo }) => {
                if (!placement) return null;
                const aspect = aspectRatioFromPx(
                  slotInfo?.natural_width_px,
                  slotInfo?.natural_height_px,
                );
                const pngUrl =
                  slotInfo?.png_path != null
                    ? buildPngUrl(projectId, slotInfo.png_path)
                    : null;
                const isInvisible = slotInfo?.sign_mode === "crypto_invisible";
                return (
                  <SignatureOverlay
                    key={slot.id}
                    pngUrl={pngUrl}
                    label={pickLocalized(slot.label, i18n.language, slot.id)}
                    xMm={placement.x_mm}
                    yMm={placement.y_mm}
                    widthMm={placement.width_mm}
                    aspectRatio={aspect}
                    pageWidthMm={pageWidthMm}
                    pageHeightMm={pageHeightMm}
                    pxPerMm={pxPerMm}
                    isInvisible={isInvisible}
                    onCommit={(next) => {
                      onPlacementChange(slot.id, {
                        x_mm: next.xMm,
                        y_mm: next.yMm,
                        width_mm: next.widthMm,
                      });
                    }}
                  />
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
};
