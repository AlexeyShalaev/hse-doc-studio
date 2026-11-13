import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  Eye,
  EyeOff,
  ExternalLink,
  ImageOff,
  MapPin,
  User,
} from "lucide-react";
import { packPlaceOf } from "@entities/signature";
import { pickLocalized } from "@shared/lib";
import {
  FreezeCard,
  SignerPlateEditor,
  SlotDetachedSignature,
} from "./DetachedSignatureBlocks";
import { SlotOptionalRows, type SlotOptionalControl } from "./SlotOptionalRows";
import { SlotDateMarks, type SlotDateRoute } from "./SlotDateMarks";
import { PlaceOriginMark } from "./PlaceOriginMark";
import { signatureHeightMm } from "../lib/coords";
import type { DateMarksSave } from "../lib/dateMarkEdit";
import type {
  PackDateMarkResponse,
  PackPlaceResponse,
  SignMode,
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
  // Только у рантайм-слотов (signing-route.md, 13.3): пак запрещает необязательность и точки,
  // чей маршрут включил слот сверх точки.
  required?: boolean;
  extra_by?: Record<string, SignatureProfileRef[]>;
  // Только у рантайм-слотов (15.11): место и метки даты из пака по документам.
  default_placements?: Record<string, PackPlaceResponse>;
  default_dates?: Record<string, PackDateMarkResponse[]>;
};

/**
 * «Вернуть место из шаблона» у слотов документа (docs/design/signing-route.md, 15.6). Пометка
 * места видна всегда, кнопка только при `canRestore`. На документе под маршрутом строка вне
 * `inert`: место возвращают сценарием маршрута, как метки даты (14.6).
 */
export type PlaceRestoreControl = {
  canRestore: boolean;
  isRestoring: (slotId: string) => boolean;
  onRestore: (slotId: string) => void;
};

/**
 * Метки даты у слотов документа (docs/design/signing-route.md, 14.2): правка и ручная дата. На
 * документе под маршрутом метки правят и на подписании (14.6), поэтому они вне `inert`.
 */
export type SlotDateControl = {
  /** Можно править метки (те же, кто размещает подписи). */
  canEdit: boolean;
  /** Слот это пара маршрута, который держит документ; null вне маршрута. */
  route: (slotId: string) => SlotDateRoute | null;
  isSaving: (slotId: string) => boolean;
  onSave: (slotId: string, body: DateMarksSave) => void;
};

export type DocPlacementPanelProps = {
  projectId: string;
  docId: string;
  // Есть ли собранный PDF: без него нельзя зафиксировать файл на подпись.
  pdfAvailable: boolean;
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
  // Переключает слот между картинкой и открепленной ЭП (надпись + файл подписи).
  onSlotModeChange: (slotId: string, mode: SignMode) => void;
  /**
   * «Показать» картинку, которую придержал маршрут подписания до согласия подписанта
   * (docs/design/signing-route.md, 5.6). Без обработчика пометка видна, кнопки нет.
   */
  onReleaseWithheld?: (slotId: string) => void;
  /** Документ держит идущий маршрут подписания: фиксирует его только маршрут. */
  routeHeld?: boolean;
  /**
   * Документ на подписании (signing-route.md, 5.5): правки слотов закрыты (`inert`), открыта только
   * отметка «Подпись необязательна» (13.9).
   */
  locked?: boolean;
  /** «Подпись необязательна» у слотов документа; без него строк с галочкой нет. */
  optionalControl?: SlotOptionalControl;
  /** Метки даты у слотов; без него блока дат нет. */
  dateControl?: SlotDateControl;
  /** Пометка «Место из шаблона» и «Вернуть место из шаблона»; без него пометки нет. */
  placeControl?: PlaceRestoreControl;
};

const lockedStyle = { opacity: 0.6 } as const;

const MIN_CAPTION_WIDTH_MM = 70;

export const DocPlacementPanel = ({
  projectId,
  docId,
  pdfAvailable,
  slotDefs,
  state,
  lang,
  currentPage,
  pageCount,
  personNameForSlot,
  onPlacementChange,
  onJumpToPage,
  onOpenProjectSignatures,
  onSlotModeChange,
  onReleaseWithheld,
  routeHeld = false,
  locked = false,
  optionalControl,
  dateControl,
  placeControl,
}: DocPlacementPanelProps) => {
  const { t } = useTranslation("signatureStamper");
  const docSlots = slotDefs.filter((slot) => slot.applies_to.includes(docId));
  const frozen = state.frozen?.[docId];
  const docSignatures = state.detached?.[docId] ?? {};
  const withheld = new Set(state.withheld?.[docId] ?? []);
  const hasDetachedSlot =
    docSlots.some(
      (slot) => state.slots[slot.id]?.sign_mode === "detached_text",
    ) || frozen !== undefined;

  if (docSlots.length === 0) {
    return (
      <div
        className="dim"
        style={{
          padding: "1.125rem",
          fontSize: "0.78125rem",
          textAlign: "center",
        }}
      >
        {t("docPlacement.noSlots")}
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ minHeight: 0 }}>
      <div inert={locked} style={locked ? lockedStyle : undefined}>
        <div
          style={{
            padding: "0.75rem 0.875rem",
            borderBottom: "1px solid var(--border)",
            fontSize: "0.6875rem",
            color: "var(--fg-2)",
            lineHeight: 1.5,
          }}
        >
          {t("docPlacement.intro")}
          <button
            type="button"
            className="btn xs ghost"
            style={{ marginTop: "0.5rem" }}
            onClick={onOpenProjectSignatures}
          >
            <ExternalLink size="0.625rem" />
            {t("docPlacement.managePng")}
          </button>
        </div>
        {hasDetachedSlot && (
          <FreezeCard
            projectId={projectId}
            docId={docId}
            frozen={frozen}
            signatureCount={Object.keys(docSignatures).length}
            pdfAvailable={pdfAvailable}
            routeHeld={routeHeld}
          />
        )}
      </div>
      {docSlots.map((slot, i) => {
        const slotInfo = state.slots[slot.id];
        const placement = state.placements[docId]?.[slot.id];
        const label = pickLocalized(slot.label, lang, slot.id);
        const personName = personNameForSlot(slot.id);
        const isDetached = slotInfo?.sign_mode === "detached_text";
        const hasPng = slotInfo?.png_path != null || isDetached;
        const isEnabled = Boolean(placement?.enabled);
        const packPlace = packPlaceOf(slot, docId);
        const placedPage = placement?.page ?? packPlace.page;
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
              padding: "0.75rem 0.875rem",
              borderBottom:
                i < docSlots.length - 1 ? "1px solid var(--border)" : 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
              opacity: hasPng ? 1 : 0.7,
            }}
          >
            {/* На подписании правки слота закрыты, открыта только отметка «необязательна». */}
            <div
              className="flex items-center"
              style={{ gap: "0.625rem", ...(locked ? lockedStyle : {}) }}
              inert={locked}
              data-testid={`doc-slot-edit-${slot.id}`}
            >
              <div
                className="flex items-center justify-center shrink-0"
                style={{
                  width: "2rem",
                  height: "2rem",
                  borderRadius: "50%",
                  background: "var(--bg-2)",
                  border: "1px solid var(--border)",
                  color: "var(--fg-3)",
                }}
              >
                <User size="0.875rem" />
              </div>
              <div
                className="flex flex-col"
                style={{ flex: 1, minWidth: 0, gap: 1 }}
              >
                <strong
                  className="truncate"
                  style={{ fontSize: "0.78125rem", color: "var(--fg-0)" }}
                >
                  {personName ?? (
                    <span className="dim">
                      {t("docPlacement.personUnknown")}
                    </span>
                  )}
                </strong>
                <span
                  className="dim truncate"
                  style={{ fontSize: "0.65625rem" }}
                >
                  {label}
                  {requiredAt.length > 0 && (
                    <span
                      style={{ color: "var(--c-warn)", marginLeft: "0.375rem" }}
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
                  style={{
                    gap: "0.375rem",
                    fontSize: "0.6875rem",
                    cursor: "pointer",
                  }}
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
                        // Надпись шире картинки: на узкой рамке она переносится
                        // на 4-5 строк, поэтому подпись не меньше 70 мм.
                        ...(next && !isEnabled && isDetached
                          ? {
                              width_mm: Math.max(
                                placement?.width_mm ?? packPlace.width_mm,
                                MIN_CAPTION_WIDTH_MM,
                              ),
                            }
                          : {}),
                      });
                    }}
                  />
                  <span>{t("docPlacement.enabled")}</span>
                </label>
              ) : (
                <span
                  className="flex items-center gap-1 shrink-0"
                  style={{ fontSize: "0.65625rem", color: "var(--c-warn)" }}
                >
                  <ImageOff size="0.6875rem" /> {t("docPlacement.noPng")}
                </span>
              )}
            </div>

            {placeControl && isEnabled && (
              <PlaceOriginMark
                placement={placement}
                canRestore={placeControl.canRestore}
                pending={placeControl.isRestoring(slot.id)}
                onRestore={() => {
                  placeControl.onRestore(slot.id);
                }}
                slotId={slot.id}
                indent
              />
            )}

            {optionalControl && (
              <SlotOptionalRows
                docId={docId}
                slot={slot}
                state={state}
                lang={lang}
                control={optionalControl}
              />
            )}

            <div
              className="flex flex-col"
              style={{ gap: "0.5rem", ...(locked ? lockedStyle : {}) }}
              inert={locked}
            >
              {withheld.has(slot.id) && (
                // Маршрут подписания придержал картинку до согласия подписанта. После отмены маршрута
                // она так и остаётся скрытой: отмена не согласие. Показать можно только явно.
                <div
                  className="flex items-center"
                  style={{
                    gap: "0.375rem",
                    paddingLeft: "2.625rem",
                    fontSize: "0.65625rem",
                    flexWrap: "wrap",
                  }}
                  data-testid={`doc-withheld-${slot.id}`}
                >
                  <span
                    className="flex items-center gap-1"
                    style={{ color: "var(--c-warn)" }}
                    title={t("docPlacement.withheldTitle")}
                  >
                    <EyeOff size="0.6875rem" aria-hidden="true" />
                    {t("docPlacement.withheld")}
                  </span>
                  {onReleaseWithheld && (
                    <button
                      type="button"
                      className="btn xs"
                      title={t("docPlacement.withheldShowTitle")}
                      data-testid={`doc-withheld-show-${slot.id}`}
                      onClick={() => {
                        onReleaseWithheld(slot.id);
                      }}
                    >
                      <Eye size="0.625rem" aria-hidden="true" />
                      {t("docPlacement.withheldShow")}
                    </button>
                  )}
                </div>
              )}

              <div
                className="flex items-center"
                style={{
                  gap: "0.375rem",
                  paddingLeft: "2.625rem",
                  fontSize: "0.65625rem",
                }}
                title={t("detached.mode.hint")}
              >
                <span className="dim">{t("detached.mode.title")}</span>
                {(["image", "detached_text"] as const).map((mode) => {
                  const active =
                    (isDetached ? "detached_text" : "image") === mode;
                  return (
                    <button
                      key={mode}
                      type="button"
                      className={active ? "btn xs" : "btn xs ghost"}
                      aria-pressed={active}
                      style={
                        active
                          ? {
                              background: "var(--accent-soft)",
                              color: "var(--accent)",
                            }
                          : undefined
                      }
                      onClick={() => {
                        if (!active) onSlotModeChange(slot.id, mode);
                      }}
                    >
                      {mode === "image"
                        ? t("detached.mode.image")
                        : t("detached.mode.detached")}
                    </button>
                  );
                })}
              </div>

              {hasPng && isEnabled && (
                <div
                  className="flex items-center"
                  style={{
                    gap: "0.375rem",
                    fontSize: "0.65625rem",
                    paddingLeft: "2.625rem",
                    flexWrap: "wrap",
                  }}
                >
                  <label
                    className="flex items-center"
                    style={{ gap: "0.3125rem" }}
                    title={t("docPlacement.signDateTitle")}
                  >
                    <span className="dim">{t("docPlacement.signDate")}</span>
                    <input
                      type="date"
                      className="input"
                      style={{
                        height: "1.375rem",
                        fontSize: "0.65625rem",
                        padding: "0 0.375rem",
                      }}
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
                      padding: "1px 0.375rem",
                      borderRadius: "0.1875rem",
                      background: isOnThisPage
                        ? "var(--c-ok-soft)"
                        : "var(--bg-2)",
                      color: isOnThisPage ? "var(--c-ok)" : "var(--fg-2)",
                    }}
                  >
                    <MapPin size="0.5625rem" />{" "}
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
                        <ArrowRight size="0.625rem" />
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

              {isDetached && (
                <SignerPlateEditor
                  projectId={projectId}
                  slotId={slot.id}
                  signer={slotInfo?.signer}
                  personName={personName}
                />
              )}

              {isDetached && (
                <SlotDetachedSignature
                  projectId={projectId}
                  docId={docId}
                  slotId={slot.id}
                  label={label}
                  personName={personName}
                  frozen={frozen}
                  signature={docSignatures[slot.id]}
                  routeHeld={routeHeld}
                />
              )}

              {!hasPng && (
                <div
                  style={{
                    paddingLeft: "2.625rem",
                    fontSize: "0.65625rem",
                    color: "var(--fg-2)",
                  }}
                >
                  {t("docPlacement.uploadPromptPrefix")}{" "}
                  <button
                    type="button"
                    className="btn xs ghost"
                    onClick={onOpenProjectSignatures}
                    style={{
                      height: "1rem",
                      padding: "0 0.375rem",
                      fontSize: "0.625rem",
                    }}
                  >
                    {t("docPlacement.toolsSignatures")}
                  </button>
                </div>
              )}
            </div>

            {dateControl && (
              <SlotDateMarks
                slotId={slot.id}
                placement={placement}
                lang={lang}
                currentPage={currentPage}
                pageCount={pageCount}
                signatureHeightMm={signatureHeightMm(
                  placement?.width_mm ?? packPlace.width_mm,
                  slotInfo,
                )}
                signerName={personName ?? label}
                route={dateControl.route(slot.id)}
                editable={dateControl.canEdit}
                pending={dateControl.isSaving(slot.id)}
                onSave={(body) => {
                  dateControl.onSave(slot.id, body);
                }}
                onJumpToPage={onJumpToPage}
              />
            )}
          </div>
        );
      })}
    </div>
  );
};
