import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  CalendarPlus,
  MapPin,
  TextAlignCenter,
  TextAlignEnd,
  TextAlignStart,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import {
  DATE_MARK_FORMATS,
  DATE_MARKS_MAX,
  dateMarkFits,
  formatDateMark,
  longestDateText,
  todayInDisplayZone,
  type DateMarkAlign,
  type DateMarkFormat,
} from "@entities/signature";
import type { PlacementResponse } from "@shared/api/types";
import {
  marksOf,
  newDateMark,
  removeMark,
  replaceMark,
  type DateMarksSave,
} from "../lib/dateMarkEdit";
import { DATE_MARK_COLOR } from "./DateMarkOverlay";

/**
 * Слот документа в маршруте, который держит документ: дату его меток даёт согласие участника
 * (docs/design/signing-route.md, 14.4), ручной даты у него нет. `method` способ участника: метки
 * даты добавляют подписанту ЭП согласование до фиксации.
 */
export type SlotDateRoute = { method: "image" | "detached" | "pades" | null };

export type SlotDateMarksProps = {
  slotId: string;
  placement: PlacementResponse | undefined;
  /** Язык документа: месяц в примере. */
  lang: string;
  currentPage: number;
  pageCount: number;
  /** Высота рамки подписи, мм: новая метка встаёт под ней. */
  signatureHeightMm: number;
  /** Кто подписывает: «Дата появится, когда {персона} подпишет». */
  signerName: string;
  /** null: слот вне маршрута, дату указывает автор. */
  route: SlotDateRoute | null;
  /** Метки можно править; иначе только видны. */
  editable: boolean;
  /** Сохранение этого слота идёт: кнопки ждут. */
  pending: boolean;
  onSave: (body: DateMarksSave) => void;
  onJumpToPage: (page: number) => void;
  /** Отступ под аватар слота, как у строк панели «Подписи» документа. */
  indent?: boolean;
};

const ALIGNS: { value: DateMarkAlign; icon: typeof TextAlignStart }[] = [
  { value: "left", icon: TextAlignStart },
  { value: "center", icon: TextAlignCenter },
  { value: "right", icon: TextAlignEnd },
];

const selectStyle = {
  fontSize: "0.6875rem",
  background: "var(--bg-2)",
  border: "1px solid var(--border)",
  borderRadius: "0.25rem",
  padding: "0.125rem 0.25rem",
  color: "var(--fg-0)",
  minWidth: 0,
  maxWidth: "100%",
} as const;

const hintStyle = {
  fontSize: "0.65625rem",
  color: "var(--fg-2)",
  lineHeight: 1.45,
} as const;

const warnStyle = {
  fontSize: "0.65625rem",
  color: "var(--c-warn)",
  lineHeight: 1.45,
  display: "flex",
  alignItems: "flex-start",
  gap: "0.25rem",
} as const;

/**
 * Метки даты слота документа в панели размещения (14.2, 14.11): «Добавить дату», у каждой метки
 * «Формат» с примером на сегодня, «Выравнивание», страница и «Удалить дату»; у слота вне маршрута
 * поле «Дата подписи». Рамки этих меток лежат на превью страницы (`PdfStampEditor`).
 */
export const SlotDateMarks = ({
  slotId,
  placement,
  lang,
  currentPage,
  pageCount,
  signatureHeightMm,
  signerName,
  route,
  editable,
  pending,
  onSave,
  onJumpToPage,
  indent = true,
}: SlotDateMarksProps) => {
  const { t } = useTranslation("signatureStamper");
  const dates = placement?.dates ?? [];
  const marks = marksOf(placement);
  const today = todayInDisplayZone();
  const signedAt = placement?.signed_at ?? null;
  const manualDate = signedAt?.source === "manual" ? signedAt.at : "";
  const disabled = !editable || pending;
  const crypto = route?.method === "detached" || route?.method === "pades";

  const save = (next: DateMarksSave) => {
    if (!disabled) onSave(next);
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.4375rem", paddingLeft: indent ? "2.625rem" : 0 }}
      data-testid={`slot-dates-${slotId}`}
    >
      {dates.map((mark, index) => {
        const sample = mark.text ?? formatDateMark(today, mark.format, lang);
        const fits = dateMarkFits(
          mark.text ?? longestDateText(mark.format, lang),
          mark.width_mm,
          mark.height_mm,
        );
        const pageMissing = pageCount > 0 && mark.page > pageCount;
        const onThisPage = mark.page === currentPage;
        return (
          <div
            key={`${mark.id}:${String(index)}`}
            className="flex flex-col"
            style={{
              gap: "0.3125rem",
              padding: "0.4375rem 0.5rem",
              borderRadius: "0.3125rem",
              border: `1px dashed color-mix(in oklch, ${DATE_MARK_COLOR} 55%, transparent)`,
              background: `color-mix(in oklch, ${DATE_MARK_COLOR} 5%, transparent)`,
            }}
            data-testid={`slot-date-${slotId}-${String(index)}`}
          >
            <div
              className="flex items-center"
              style={{
                gap: "0.375rem",
                flexWrap: "wrap",
                fontSize: "0.65625rem",
              }}
            >
              <strong style={{ color: DATE_MARK_COLOR, fontWeight: 600 }}>
                {t("dates.frame", { sample })}
              </strong>
              <span
                className="flex items-center gap-1 mono"
                style={{
                  padding: "1px 0.375rem",
                  borderRadius: "0.1875rem",
                  background: onThisPage ? "var(--c-ok-soft)" : "var(--bg-2)",
                  color: onThisPage ? "var(--c-ok)" : "var(--fg-2)",
                }}
              >
                <MapPin size="0.5625rem" aria-hidden="true" />
                {t("dates.page", { page: mark.page })}
              </span>
              {!onThisPage && (
                <>
                  {!pageMissing && (
                    <button
                      type="button"
                      className="btn xs ghost"
                      onClick={() => {
                        onJumpToPage(mark.page);
                      }}
                    >
                      <ArrowRight size="0.625rem" aria-hidden="true" />
                      {t("dates.jump")}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn xs"
                    disabled={disabled || pageCount === 0}
                    title={t("dates.moveHereTitle", { page: currentPage })}
                    onClick={() => {
                      save({
                        dates: replaceMark(marks, index, { page: currentPage }),
                      });
                    }}
                  >
                    {t("dates.moveHere")}
                  </button>
                </>
              )}
            </div>
            <div
              className="flex items-center"
              style={{ gap: "0.375rem", flexWrap: "wrap" }}
            >
              <label
                className="flex items-center"
                style={{
                  gap: "0.3125rem",
                  minWidth: 0,
                  fontSize: "0.65625rem",
                }}
              >
                <span className="dim">{t("dates.format")}</span>
                <select
                  style={selectStyle}
                  value={mark.format}
                  disabled={disabled}
                  data-testid={`slot-date-format-${slotId}-${String(index)}`}
                  onChange={(e) => {
                    save({
                      dates: replaceMark(marks, index, {
                        format: e.target.value as DateMarkFormat,
                      }),
                    });
                  }}
                >
                  {DATE_MARK_FORMATS.map((format) => (
                    <option key={format} value={format}>
                      {t("dates.formatOption", {
                        name: t(`dates.formats.${format}`),
                        example: formatDateMark(today, format, lang),
                      })}
                    </option>
                  ))}
                </select>
              </label>
              <div
                role="group"
                aria-label={t("dates.align")}
                className="flex items-center"
                style={{ gap: "0.125rem", fontSize: "0.65625rem" }}
              >
                <span className="dim" style={{ marginRight: "0.1875rem" }}>
                  {t("dates.align")}
                </span>
                {ALIGNS.map(({ value, icon: Icon }) => {
                  const on = mark.align === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      className={on ? "btn xs" : "btn xs ghost"}
                      aria-pressed={on}
                      aria-label={t(`dates.aligns.${value}`)}
                      title={t(`dates.aligns.${value}`)}
                      disabled={disabled}
                      style={
                        on
                          ? {
                              background: "var(--accent-soft)",
                              color: "var(--accent)",
                            }
                          : undefined
                      }
                      onClick={() => {
                        if (!on)
                          save({
                            dates: replaceMark(marks, index, { align: value }),
                          });
                      }}
                    >
                      <Icon size="0.6875rem" aria-hidden="true" />
                    </button>
                  );
                })}
              </div>
              {editable && (
                <button
                  type="button"
                  className="btn xs ghost"
                  disabled={disabled}
                  style={{ color: "var(--c-err)", marginLeft: "auto" }}
                  data-testid={`slot-date-remove-${slotId}-${String(index)}`}
                  onClick={() => {
                    save({ dates: removeMark(marks, index) });
                  }}
                >
                  <Trash2 size="0.625rem" aria-hidden="true" />
                  {t("dates.remove")}
                </button>
              )}
            </div>
            {!fits && (
              <span style={warnStyle} role="status">
                <TriangleAlert
                  size="0.6875rem"
                  aria-hidden="true"
                  style={{ flexShrink: 0, marginTop: "0.0625rem" }}
                />
                {t("dates.tooSmall")}
              </span>
            )}
            {pageMissing && (
              <span style={warnStyle} role="status">
                <TriangleAlert
                  size="0.6875rem"
                  aria-hidden="true"
                  style={{ flexShrink: 0, marginTop: "0.0625rem" }}
                />
                {t("dates.pageMissing", { page: mark.page })}
              </span>
            )}
          </div>
        );
      })}

      {editable && (
        <div>
          <button
            type="button"
            className="btn xs"
            disabled={
              disabled || pageCount === 0 || dates.length >= DATE_MARKS_MAX
            }
            title={
              dates.length >= DATE_MARKS_MAX
                ? t("dates.limit", { max: DATE_MARKS_MAX })
                : t("dates.addTitle", { page: currentPage })
            }
            data-testid={`slot-date-add-${slotId}`}
            onClick={() => {
              save({
                dates: [
                  ...marks,
                  newDateMark(placement, currentPage, signatureHeightMm),
                ],
              });
            }}
          >
            <CalendarPlus size="0.6875rem" aria-hidden="true" />
            {t("dates.add")}
          </button>
        </div>
      )}

      {dates.length > 0 && route === null && (
        <div className="flex flex-col" style={{ gap: "0.1875rem" }}>
          <label
            className="flex items-center"
            style={{ gap: "0.3125rem", fontSize: "0.65625rem" }}
            title={t("dates.signedAtTitle")}
          >
            <span className="dim">{t("dates.signedAt")}</span>
            <input
              type="date"
              className="input"
              disabled={disabled}
              data-testid={`slot-date-signed-at-${slotId}`}
              style={{
                height: "1.375rem",
                fontSize: "0.65625rem",
                padding: "0 0.375rem",
              }}
              value={manualDate}
              onChange={(e) => {
                save({
                  dates: marks,
                  signed_at: e.target.value ? { date: e.target.value } : null,
                });
              }}
            />
          </label>
          {manualDate === "" && (
            <span style={hintStyle}>{t("dates.noDate")}</span>
          )}
        </div>
      )}

      {dates.length > 0 && route !== null && (
        <div className="flex flex-col" style={{ gap: "0.1875rem" }}>
          <span style={hintStyle}>
            {signedAt === null
              ? t("dates.waits", { persona: signerName })
              : t("dates.fromRoute")}
          </span>
          {crypto && <span style={hintStyle}>{t("dates.esign")}</span>}
        </div>
      )}
    </div>
  );
};
