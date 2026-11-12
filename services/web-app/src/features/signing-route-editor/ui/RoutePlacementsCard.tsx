import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { MapPin, Plus, X } from "lucide-react";
import { getDocMeta, type DocDefLike } from "@entities/document";
import { useUpdateSignaturePlacement } from "@entities/signature";
import type {
  RouteSlotRef,
  SigningRoute,
  SigningRoutePreview,
} from "@entities/signing-route";
import { PdfStampEditor } from "@features/signature-stamper";
import type { SignaturesStateResponse } from "@shared/api/types";
import { pickLocalized } from "@shared/lib";
import { ViewTabs } from "@shared/ui";

export type RoutePlacementsCardProps = {
  projectId: string;
  route: SigningRoute;
  preview: SigningRoutePreview | undefined;
  editable: boolean;
  busy: boolean;
  state: SignaturesStateResponse | undefined;
  documents: readonly (DocDefLike & { id: string })[] | undefined;
  personaLabel: (persona: string) => string;
  onAddExtra: (slot: RouteSlotRef) => void;
  onRemoveExtra: (slot: RouteSlotRef) => void;
  /**
   * «Подпись необязательна» на точке маршрута (docs/design/signing-route.md, 13.9); без него
   * галочек нет.
   */
  onSetOptional?: (slot: RouteSlotRef, optional: boolean) => void;
  /** Пара, отметка которой сейчас сохраняется. */
  optionalPending?: RouteSlotRef | null;
  /**
   * Слот, к которому привела помеха «подпись не размещена»: открыть его документ, прокрутить
   * к нему и подсветить. `n` растёт с каждым переходом, чтобы повторный переход тоже сработал.
   */
  focus?: (RouteSlotRef & { n: number }) | null;
};

// Надпись открепленной ЭП шире картинки: на узкой рамке она переносится на 4-5 строк.
const MIN_CAPTION_WIDTH_MM = 70;

/**
 * «Где подписи»: вкладки документов маршрута и тот же редактор размещения, что на вкладке
 * «Подписи», но только со слотами маршрута. Слоты, которые точка не требует, добавляются здесь
 * («добавлена вами»), и здесь же подпись отмечается необязательной на точке маршрута.
 */
export const RoutePlacementsCard = ({
  projectId,
  route,
  preview,
  editable,
  busy,
  state,
  documents,
  personaLabel,
  onAddExtra,
  onRemoveExtra,
  onSetOptional,
  optionalPending = null,
  focus = null,
}: RoutePlacementsCardProps) => {
  const { t, i18n } = useTranslation("signingRouteEditor");
  const lang = i18n.language;
  const [docId, setDocId] = useState(route.docs[0]?.doc_id ?? "");
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const { mutate: updatePlacement } = useUpdateSignaturePlacement();
  // Переход от помехи: документ слота выбирается при рендере (без эффекта), прокрутка после него.
  const [seenFocus, setSeenFocus] = useState(0);
  if (focus !== null && focus.n !== seenFocus) {
    setSeenFocus(focus.n);
    setDocId(focus.doc_id);
    setPage(1);
  }
  const rootRef = useRef<HTMLDivElement>(null);
  const focusN = focus?.n ?? 0;
  const focusSlot = focus?.slot_id ?? null;
  useEffect(() => {
    if (focusN === 0 || focusSlot === null) return;
    const row = rootRef.current?.querySelector<HTMLElement>(
      `[data-slot-row="${CSS.escape(focusSlot)}"]`,
    );
    const target = row ?? rootRef.current;
    // В тестовом окружении (jsdom) прокрутки нет.
    if (target && typeof target.scrollIntoView === "function")
      target.scrollIntoView({ block: "center", behavior: "smooth" });
    row
      ?.querySelector<HTMLElement>("[data-place]")
      ?.focus({ preventScroll: true });
  }, [focusN, focusSlot]);
  const doc = route.docs.find((d) => d.doc_id === docId) ?? route.docs[0];
  if (!doc) return null;

  const people = new Map(route.steps.flat().map((p) => [p.id, p]));
  const runtime = state?.runtime_slots ?? [];
  const inRoute = new Set(doc.slots.map((s) => s.slot_id));
  const slotDefs = runtime.filter(
    (s) => inRoute.has(s.id) && s.applies_to.includes(doc.doc_id),
  );
  // Слоты сверх точки: применимы к документу, но точка их не требует.
  const candidates = editable
    ? runtime.filter(
        (s) => s.applies_to.includes(doc.doc_id) && !inRoute.has(s.id),
      )
    : [];
  const built =
    preview?.docs.find((d) => d.doc_id === doc.doc_id)?.built ?? false;
  const pdfRelPath = getDocMeta(
    doc.doc_id,
    documents?.find((d) => d.id === doc.doc_id),
  ).out;

  const placementOf = (slotId: string) =>
    state?.placements[doc.doc_id]?.[slotId];

  return (
    <div ref={rootRef} className="flex flex-col" style={{ gap: "0.75rem" }}>
      {route.docs.length > 1 && (
        <ViewTabs
          views={route.docs.map((d) => ({
            value: d.doc_id,
            label: pickLocalized(d.name, lang, d.doc_id),
          }))}
          value={doc.doc_id}
          onChange={(next) => {
            setDocId(next);
            setPage(1);
          }}
        />
      )}
      {!state ? (
        <p className="dim" style={{ margin: 0, fontSize: "0.75rem" }}>
          {t("placements.noState")}
        </p>
      ) : (
        <div
          className="doc-signatures-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "16rem minmax(0, 1fr)",
            minHeight: "30rem",
            height: "36rem",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-2)",
            overflow: "hidden",
          }}
        >
          <div
            className="flex flex-col"
            style={{
              borderRight: "1px solid var(--border)",
              background: "var(--bg-1)",
              overflowY: "auto",
              minHeight: 0,
            }}
          >
            {doc.slots.map((slot) => {
              const owner =
                slot.participant_id === null
                  ? undefined
                  : people.get(slot.participant_id);
              const placement = placementOf(slot.slot_id);
              const def = runtime.find((s) => s.id === slot.slot_id);
              const placedPage =
                placement?.page ?? def?.default_placement.page ?? 1;
              const isDetached =
                state.slots[slot.slot_id]?.sign_mode === "detached_text";
              return (
                <div
                  key={slot.slot_id}
                  className="flex flex-col"
                  style={{
                    gap: "0.375rem",
                    padding: "0.625rem 0.75rem",
                    borderBottom: "1px solid var(--border)",
                    fontSize: "0.71875rem",
                    // Слот, к которому привела помеха отправки.
                    boxShadow:
                      focus !== null &&
                      focus.doc_id === doc.doc_id &&
                      focus.slot_id === slot.slot_id &&
                      !placement?.enabled
                        ? "inset 0.1875rem 0 0 var(--c-warn)"
                        : undefined,
                  }}
                  data-testid={`route-slot-${slot.slot_id}`}
                  data-slot-row={slot.slot_id}
                >
                  <div
                    className="flex items-center"
                    style={{ gap: "0.375rem" }}
                  >
                    <strong
                      className="truncate"
                      style={{ flex: 1, fontSize: "0.75rem" }}
                    >
                      {pickLocalized(slot.label, lang, slot.slot_id)}
                    </strong>
                    {slot.extra && editable && (
                      <button
                        type="button"
                        className="icon-btn"
                        disabled={busy}
                        aria-label={t("placements.removeExtra")}
                        title={t("placements.removeExtra")}
                        onClick={() => {
                          onRemoveExtra({
                            doc_id: doc.doc_id,
                            slot_id: slot.slot_id,
                          });
                        }}
                      >
                        <X size="0.75rem" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                  <span className="dim">
                    {owner
                      ? (owner.name ?? personaLabel(owner.persona))
                      : t("placements.nobody")}
                    {slot.extra && ` · ${t("placements.extra")}`}
                  </span>
                  {onSetOptional && (
                    <OptionalToggle
                      checked={slot.optional}
                      // Снять отметку можно всегда; отметить нельзя подпись, которую требует
                      // шаблон или которая уже стоит.
                      blocker={
                        slot.optional
                          ? null
                          : def?.required === true
                            ? t("placements.optionalRequired")
                            : slot.status === "signed"
                              ? t("placements.optionalSigned")
                              : null
                      }
                      pending={
                        optionalPending?.doc_id === doc.doc_id &&
                        optionalPending.slot_id === slot.slot_id
                      }
                      testId={`route-optional-${slot.slot_id}`}
                      onChange={(next) => {
                        onSetOptional(
                          { doc_id: doc.doc_id, slot_id: slot.slot_id },
                          next,
                        );
                      }}
                    />
                  )}
                  {editable && (
                    <div
                      className="flex items-center"
                      style={{ gap: "0.375rem", flexWrap: "wrap" }}
                    >
                      {placement?.enabled ? (
                        <>
                          <span
                            className="chip subtle"
                            style={{
                              color:
                                placedPage === page ? "var(--c-ok)" : undefined,
                            }}
                          >
                            <MapPin size="0.5625rem" aria-hidden="true" />
                            {t("placements.page", { page: placedPage })}
                          </span>
                          {placedPage !== page && (
                            <>
                              <button
                                type="button"
                                className="btn xs ghost"
                                onClick={() => {
                                  setPage(placedPage);
                                }}
                              >
                                {t("placements.jump")}
                              </button>
                              <button
                                type="button"
                                className="btn xs"
                                disabled={pageCount === 0}
                                onClick={() => {
                                  updatePlacement({
                                    projectId,
                                    docId: doc.doc_id,
                                    slotId: slot.slot_id,
                                    data: { page },
                                  });
                                }}
                              >
                                {t("placements.moveHere")}
                              </button>
                            </>
                          )}
                        </>
                      ) : (
                        <>
                          <span style={{ color: "var(--c-warn)" }}>
                            {t("placements.notPlaced")}
                          </span>
                          <button
                            type="button"
                            className="btn xs"
                            data-place
                            onClick={() => {
                              updatePlacement({
                                projectId,
                                docId: doc.doc_id,
                                slotId: slot.slot_id,
                                data: {
                                  enabled: true,
                                  page,
                                  ...(isDetached
                                    ? {
                                        width_mm: Math.max(
                                          placement?.width_mm ??
                                            def?.default_placement.width_mm ??
                                            0,
                                          MIN_CAPTION_WIDTH_MM,
                                        ),
                                      }
                                    : {}),
                                },
                              });
                            }}
                          >
                            {t("placements.place", { page })}
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {candidates.length > 0 && (
              <div
                className="flex flex-col"
                style={{ gap: "0.375rem", padding: "0.625rem 0.75rem" }}
              >
                {candidates.map((slot) => (
                  <button
                    key={slot.id}
                    type="button"
                    className="btn xs ghost"
                    // Длинное название слота переносится, а не обрезается краем колонки.
                    style={{
                      justifyContent: "flex-start",
                      height: "auto",
                      minHeight: "1.5rem",
                      padding: "0.25rem 0.5rem",
                      whiteSpace: "normal",
                      textAlign: "left",
                    }}
                    disabled={busy}
                    onClick={() => {
                      onAddExtra({ doc_id: doc.doc_id, slot_id: slot.id });
                    }}
                    data-testid={`route-add-slot-${slot.id}`}
                  >
                    <Plus
                      size="0.6875rem"
                      aria-hidden="true"
                      style={{ flexShrink: 0 }}
                    />
                    {t("placements.add", {
                      label: pickLocalized(slot.label, lang, slot.id),
                    })}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-col" style={{ minHeight: 0, minWidth: 0 }}>
            <PdfStampEditor
              projectId={projectId}
              docId={doc.doc_id}
              pdfRelPath={pdfRelPath}
              pdfAvailable={built}
              slotDefs={slotDefs}
              state={state}
              page={page}
              onPageChange={setPage}
              onPageCountChange={setPageCount}
              onPlacementChange={(slotId, patch) => {
                if (!editable) return;
                updatePlacement({
                  projectId,
                  docId: doc.doc_id,
                  slotId,
                  data: patch,
                });
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

/** Галочка «Подпись необязательна» у слота маршрута; причина, почему нельзя, видна под ней. */
const OptionalToggle = ({
  checked,
  blocker,
  pending,
  testId,
  onChange,
}: {
  checked: boolean;
  blocker: string | null;
  pending: boolean;
  testId: string;
  onChange: (next: boolean) => void;
}) => {
  const { t } = useTranslation("signingRouteEditor");
  const note = blocker ?? (checked ? t("placements.optionalHint") : null);
  return (
    <div className="flex flex-col" style={{ gap: "0.125rem" }}>
      <label
        className="flex items-center"
        style={{
          gap: "0.375rem",
          cursor: blocker === null ? "pointer" : "default",
          color: blocker === null ? undefined : "var(--fg-3)",
        }}
        title={t("placements.optionalHint")}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={blocker !== null || pending}
          data-testid={testId}
          onChange={(e) => {
            onChange(e.target.checked);
          }}
        />
        {t("placements.optional")}
      </label>
      {note !== null && (
        <span className="dim" style={{ paddingLeft: "1.25rem" }}>
          {note}
        </span>
      )}
    </div>
  );
};
