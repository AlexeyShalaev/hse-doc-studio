import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";
import { clampWidthMm } from "../lib/coords";

export type SignatureOverlayProps = {
  pngUrl: string | null;
  label: string;
  xMm: number;
  yMm: number;
  widthMm: number;
  aspectRatio: number;
  pageWidthMm: number;
  pageHeightMm: number;
  pxPerMm: number;
  // crypto_invisible mode: the signed PDF carries an *invisible* signature
  // field at this box (no PNG drawn). We still render a draggable placeholder
  // so the user can position/size the field; it shows a lock instead of the
  // image to make clear nothing will be visible in the output.
  isInvisible?: boolean;
  // Called when the user finishes a drag or resize gesture. We deliberately
  // wait for pointer-up rather than firing on every move — the parent uses
  // this to PATCH the backend, and firing per-frame would melt the network.
  onCommit: (next: { xMm: number; yMm: number; widthMm: number }) => void;
};

type Gesture =
  | { kind: "idle" }
  | {
      kind: "drag";
      pointerId: number;
      startX: number;
      startY: number;
      baseX: number;
      baseY: number;
    }
  | {
      kind: "resize";
      pointerId: number;
      startX: number;
      baseWidthMm: number;
    };

export const SignatureOverlay = ({
  pngUrl,
  label,
  xMm,
  yMm,
  widthMm,
  aspectRatio,
  pageWidthMm,
  pageHeightMm,
  pxPerMm,
  isInvisible = false,
  onCommit,
}: SignatureOverlayProps) => {
  const { t } = useTranslation("signatureStamper");
  // Mirror the canonical mm values locally so the drag feels instant: pointer
  // events update local state for the live render, and we only push the
  // committed values up on pointer-up. When the parent's xMm/yMm/widthMm
  // change (e.g. another client edited them, or we just resynced from the
  // server) we copy them back into local state via the useEffects below.
  const [localX, setLocalX] = useState(xMm);
  const [localY, setLocalY] = useState(yMm);
  const [localWidth, setLocalWidth] = useState(widthMm);
  const [isDragging, setIsDragging] = useState(false);
  const gestureRef = useRef<Gesture>({ kind: "idle" });
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (gestureRef.current.kind === "idle") setLocalX(xMm);
  }, [xMm]);
  useEffect(() => {
    if (gestureRef.current.kind === "idle") setLocalY(yMm);
  }, [yMm]);
  useEffect(() => {
    if (gestureRef.current.kind === "idle") setLocalWidth(widthMm);
  }, [widthMm]);

  const heightMm = localWidth * aspectRatio;

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = gestureRef.current;
    if (g.kind === "idle" || g.pointerId !== e.pointerId) return;
    if (g.kind === "drag") {
      const deltaXmm = (e.clientX - g.startX) / pxPerMm;
      const deltaYmm = (e.clientY - g.startY) / pxPerMm;
      const nextX = Math.min(
        Math.max(0, g.baseX + deltaXmm),
        Math.max(0, pageWidthMm - localWidth),
      );
      const nextY = Math.min(
        Math.max(0, g.baseY + deltaYmm),
        Math.max(0, pageHeightMm - heightMm),
      );
      setLocalX(nextX);
      setLocalY(nextY);
    } else {
      const deltaXmm = (e.clientX - g.startX) / pxPerMm;
      const nextWidth = clampWidthMm(g.baseWidthMm + deltaXmm);
      setLocalWidth(nextWidth);
    }
  };

  const finishGesture = (e: React.PointerEvent<HTMLDivElement>) => {
    const g = gestureRef.current;
    if (g.kind === "idle" || g.pointerId !== e.pointerId) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    gestureRef.current = { kind: "idle" };
    setIsDragging(false);
    onCommit({ xMm: localX, yMm: localY, widthMm: localWidth });
  };

  const handleBodyPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    gestureRef.current = {
      kind: "drag",
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      baseX: localX,
      baseY: localY,
    };
    setIsDragging(true);
    e.preventDefault();
  };

  const handleHandlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.currentTarget.parentElement?.setPointerCapture(e.pointerId);
    gestureRef.current = {
      kind: "resize",
      pointerId: e.pointerId,
      startX: e.clientX,
      baseWidthMm: localWidth,
    };
    setIsDragging(true);
    e.preventDefault();
  };

  return (
    <div
      ref={bodyRef}
      onPointerDown={handleBodyPointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishGesture}
      onPointerCancel={finishGesture}
      style={{
        position: "absolute",
        left: localX * pxPerMm,
        top: localY * pxPerMm,
        width: localWidth * pxPerMm,
        height: heightMm * pxPerMm,
        cursor: isDragging ? "grabbing" : "grab",
        border: isInvisible
          ? "1.5px dashed var(--fg-3)"
          : "1.5px dashed var(--accent)",
        background: isInvisible
          ? "color-mix(in oklch, var(--fg-3) 10%, transparent)"
          : "color-mix(in oklch, var(--accent) 8%, transparent)",
        boxSizing: "border-box",
        touchAction: "none",
      }}
      title={isInvisible ? t("overlay.invisibleTitle", { label }) : label}
    >
      {isInvisible ? (
        <div
          className="mono dim"
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 2,
            fontSize: 9,
            textAlign: "center",
            pointerEvents: "none",
            color: "var(--fg-2)",
          }}
        >
          <Lock size={12} />
          <span>{t("overlay.invisible")}</span>
        </div>
      ) : pngUrl ? (
        <img
          src={pngUrl}
          alt={label}
          draggable={false}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            pointerEvents: "none",
            userSelect: "none",
          }}
        />
      ) : (
        <div
          className="mono dim"
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            textTransform: "uppercase",
            pointerEvents: "none",
          }}
        >
          {label}
        </div>
      )}
      <div
        onPointerDown={handleHandlePointerDown}
        style={{
          position: "absolute",
          right: -7,
          bottom: -7,
          width: 14,
          height: 14,
          background: "var(--accent)",
          border: "2px solid var(--bg-0)",
          borderRadius: 3,
          cursor: "nwse-resize",
          touchAction: "none",
        }}
      />
    </div>
  );
};
