import { useTranslation } from "react-i18next";
import { ArrowRight, ExternalLink, ImageOff, MapPin, User } from "lucide-react";
import { pickLocalized } from "@shared/lib";
import type {
  SignatureProfileRef,
  SignaturesStateResponse,
  SignatureSlotDefResponse,
  UpdatePlacementRequest,
} from "@shared/api/types";

// Панель получает либо рантайм-слоты проекта, либо каталожные (фолбэк, когда
// версия пака не разрешилась). Обязательность знают только первые: она зависит
// от контрольной точки, а каталог описывает пак вне проекта. Поэтому поле
// необязательное, и его отсутствие читается как «сведений нет», а не «не нужна».
export type PlacementSlot = Omit<SignatureSlotDefResponse, "required_by"> & {
  required_by?: Record<string, SignatureProfileRef[]>;
};

export type DocPlacementPanelProps = {
  docId: string;
  slotDefs: readonly PlacementSlot[];
  state: SignaturesStateResponse;
  lang: string;
  // Page the PDF preview is currently showing. Used so the user can drop a
  // placement onto whatever page they're looking at without leaving the
  // editor — "Поместить на стр. N" picks up this value.
  currentPage: number;
  pageCount: number;
  personNameForSlot: (slotId: string) => string | null;
  onPlacementChange: (slotId: string, patch: UpdatePlacementRequest) => void;
  onJumpToPage: (page: number) => void;
  onOpenProjectSignatures: () => void;
};

export const DocPlacementPanel = ({
  docId,
  slotDefs,
  state,
  lang,
  currentPage,
  pageCount,
  personNameForSlot,
  onPlacementChange,
  onJumpToPage,
  onOpenProjectSignatures,
}: DocPlacementPanelProps) => {
  const { t } = useTranslation("signatureStamper");
  const docSlots = slotDefs.filter((slot) => slot.applies_to.includes(docId));

  if (docSlots.length === 0) {
    return (
      <div
        className="dim"
        style={{ padding: 18, fontSize: 12.5, textAlign: "center" }}
      >
        {t("docPlacement.noSlots")}
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ minHeight: 0 }}>
      <div
        style={{
          padding: "12px 14px",
          borderBottom: "1px solid var(--border)",
          fontSize: 11,
          color: "var(--fg-2)",
          lineHeight: 1.5,
        }}
      >
        {t("docPlacement.intro")}
        <button
          type="button"
          className="btn xs ghost"
          style={{ marginTop: 8 }}
          onClick={onOpenProjectSignatures}
        >
          <ExternalLink size={10} />
          {t("docPlacement.managePng")}
        </button>
      </div>
      {docSlots.map((slot, i) => {
        const slotInfo = state.slots[slot.id];
        const placement = state.placements[docId]?.[slot.id];
        const label = pickLocalized(slot.label, lang, slot.id);
        const personName = personNameForSlot(slot.id);
        const hasPng = slotInfo?.png_path != null;
        const isEnabled = Boolean(placement?.enabled);
        const placedPage = placement?.page ?? slot.default_placement.page;
        const isOnThisPage = placedPage === currentPage;
        // Обязательность зависит от контрольной точки, поэтому показываем не
        // «обязательно», а КОГДА: список точек, чей комплект эту подпись
        // требует. Пусто — подпись применима, но ни одним комплектом не нужна.
        const requiredAt = slot.required_by?.[docId] ?? [];
        const requiredAtNames = requiredAt
          .map((profile: SignatureProfileRef) =>
            pickLocalized(profile.name, lang, profile.id),
          )
          .join(", ");

        return (
          <div
            key={slot.id}
            style={{
              padding: "12px 14px",
              borderBottom:
                i < docSlots.length - 1 ? "1px solid var(--border)" : 0,
              display: "flex",
              flexDirection: "column",
              gap: 8,
              opacity: hasPng ? 1 : 0.7,
            }}
          >
            <div className="flex items-center" style={{ gap: 10 }}>
              <div
                className="flex items-center justify-center shrink-0"
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: "var(--bg-2)",
                  border: "1px solid var(--border)",
                  color: "var(--fg-3)",
                }}
              >
                <User size={14} />
              </div>
              <div
                className="flex flex-col"
                style={{ flex: 1, minWidth: 0, gap: 1 }}
              >
                <strong
                  className="truncate"
                  style={{ fontSize: 12.5, color: "var(--fg-0)" }}
                >
                  {personName ?? (
                    <span className="dim">
                      {t("docPlacement.personUnknown")}
                    </span>
                  )}
                </strong>
                <span className="dim truncate" style={{ fontSize: 10.5 }}>
                  {label}
                  {requiredAt.length > 0 && (
                    <span
                      style={{ color: "var(--c-warn)", marginLeft: 6 }}
                      title={t("docPlacement.requiredAtTitle", {
                        checkpoints: requiredAtNames,
                      })}
                    >
                      ·{" "}
                      {t("docPlacement.requiredAt", {
                        checkpoints: requiredAtNames,
                      })}
                    </span>
                  )}
                </span>
              </div>
              {hasPng ? (
                <label
                  className="flex items-center"
                  style={{ gap: 6, fontSize: 11, cursor: "pointer" }}
                  title={
                    isEnabled
                      ? t("docPlacement.enabledTitle")
                      : t("docPlacement.enableTitle")
                  }
                >
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    onChange={(e) => {
                      const next = e.target.checked;
                      // When turning on for the first time, snap to the current
                      // preview page so the user sees the overlay immediately
                      // instead of guessing where on page 1 it landed.
                      onPlacementChange(slot.id, {
                        enabled: next,
                        ...(next && !isEnabled ? { page: currentPage } : {}),
                      });
                    }}
                  />
                  <span>{t("docPlacement.enabled")}</span>
                </label>
              ) : (
                <span
                  className="flex items-center gap-1 shrink-0"
                  style={{ fontSize: 10.5, color: "var(--c-warn)" }}
                >
                  <ImageOff size={11} /> {t("docPlacement.noPng")}
                </span>
              )}
            </div>

            {hasPng && isEnabled && (
              <div
                className="flex items-center"
                style={{
                  gap: 6,
                  fontSize: 10.5,
                  paddingLeft: 42,
                  flexWrap: "wrap",
                }}
              >
                <label
                  className="flex items-center"
                  style={{ gap: 5 }}
                  title={t("docPlacement.signDateTitle")}
                >
                  <span className="dim">{t("docPlacement.signDate")}</span>
                  <input
                    type="date"
                    className="input"
                    style={{ height: 22, fontSize: 10.5, padding: "0 6px" }}
                    value={placement?.sign_date ?? ""}
                    onChange={(e) => {
                      // "" очищает дату — подпись штампуется без неё.
                      onPlacementChange(slot.id, {
                        sign_date: e.target.value,
                      });
                    }}
                  />
                </label>
                <span
                  className="flex items-center gap-1 mono"
                  style={{
                    padding: "1px 6px",
                    borderRadius: 3,
                    background: isOnThisPage
                      ? "var(--c-ok-soft)"
                      : "var(--bg-2)",
                    color: isOnThisPage ? "var(--c-ok)" : "var(--fg-2)",
                  }}
                >
                  <MapPin size={9} />{" "}
                  {t("docPlacement.page", { page: placedPage })}
                </span>
                {!isOnThisPage && (
                  <>
                    <button
                      type="button"
                      className="btn xs ghost"
                      onClick={() => {
                        onJumpToPage(placedPage);
                      }}
                      title={t("docPlacement.openPageTitle", {
                        page: placedPage,
                      })}
                    >
                      <ArrowRight size={10} />
                      {t("docPlacement.jump")}
                    </button>
                    <button
                      type="button"
                      className="btn xs"
                      disabled={pageCount === 0}
                      onClick={() => {
                        onPlacementChange(slot.id, { page: currentPage });
                      }}
                      title={t("docPlacement.moveToCurrentTitle", {
                        page: currentPage,
                      })}
                    >
                      {t("docPlacement.moveHere")}
                    </button>
                  </>
                )}
              </div>
            )}

            {!hasPng && (
              <div
                style={{
                  paddingLeft: 42,
                  fontSize: 10.5,
                  color: "var(--fg-2)",
                }}
              >
                {t("docPlacement.uploadPromptPrefix")}{" "}
                <button
                  type="button"
                  className="btn xs ghost"
                  onClick={onOpenProjectSignatures}
                  style={{ height: 16, padding: "0 6px", fontSize: 10 }}
                >
                  {t("docPlacement.toolsSignatures")}
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
