import { useTranslation } from "react-i18next";
import {
  CircleAlert,
  LayoutTemplate,
  PencilLine,
  RotateCcw,
} from "lucide-react";
import { placeMarkOf, placeOnLine, type AnchorNote } from "@entities/signature";
import type { PlacementResponse } from "@shared/api/types";
import { Spinner } from "@shared/ui";

export type PlaceOriginMarkProps = {
  placement: PlacementResponse | undefined;
  /** Можно вернуть место (права и документ позволяют); без этого кнопки нет. */
  canRestore: boolean;
  pending: boolean;
  onRestore: () => void;
  /** id слота: test id пометки и кнопки. */
  slotId: string;
  /** Отступ слева, чтобы строка встала под подписью слота (вкладка «Подписи»). */
  indent?: boolean;
};

/**
 * Пометка места подписи (docs/design/signing-route.md, 15.7): «Место из шаблона», если место и
 * метки даты как в шаблоне (или это затравка из пака), иначе «Место изменено» и кнопка «Вернуть
 * место из шаблона». Без места в шаблоне пометки нет. У места на строке шаблона (якорь, 15.17.14)
 * пометка уточняется: «Место по строке шаблона».
 */
export const PlaceOriginMark = ({
  placement,
  canRestore,
  pending,
  onRestore,
  slotId,
  indent = false,
}: PlaceOriginMarkProps) => {
  const { t } = useTranslation("signatureStamper");
  const mark = placeMarkOf(placement);
  if (mark === null) return null;
  const fromTemplate = mark === "template";
  const onLine = placeOnLine(placement);
  return (
    <div
      className="flex items-center"
      style={{
        gap: "0.375rem",
        flexWrap: "wrap",
        fontSize: "0.65625rem",
        paddingLeft: indent ? "2.625rem" : undefined,
      }}
      data-testid={`place-origin-${slotId}`}
      data-origin={mark}
    >
      <span
        className="chip subtle"
        title={
          onLine
            ? t("place.onLineTitle")
            : fromTemplate
              ? t("place.fromTemplateTitle")
              : t("place.changedTitle")
        }
        data-on-line={onLine ? "" : undefined}
      >
        {fromTemplate ? (
          <LayoutTemplate size="0.5625rem" aria-hidden="true" />
        ) : (
          <PencilLine size="0.5625rem" aria-hidden="true" />
        )}
        {onLine
          ? t("place.onLine")
          : fromTemplate
            ? t("place.fromTemplate")
            : t("place.changed")}
      </span>
      {!fromTemplate && canRestore && (
        <button
          type="button"
          className="btn xs ghost"
          disabled={pending}
          title={t("place.restoreTitle")}
          data-testid={`place-restore-${slotId}`}
          onClick={onRestore}
        >
          {pending ? (
            <Spinner size="sm" />
          ) : (
            <RotateCcw size="0.625rem" aria-hidden="true" />
          )}
          {t("place.restore")}
        </button>
      )}
    </div>
  );
};

const NOTE_KEYS = {
  missing: "place.anchor.missing",
  unknown: "place.anchor.unknown",
  own_pdf: "place.anchor.ownPdf",
} as const;

/**
 * Подсказка у пары, чьё место пака на строке шаблона (docs/design/signing-route.md, 15.17.14): строки
 * в собранном документе нет, место появится после сборки, у загруженного PDF строк шаблона нет.
 * Стоит вместо кнопки «Вернуть место из шаблона»: вернуть такое место нечем.
 */
export const PlaceAnchorNote = ({
  note,
  slotId,
  indent = false,
}: {
  note: AnchorNote | null;
  /** id слота: test id подсказки. */
  slotId: string;
  /** Отступ слева, чтобы строка встала под подписью слота (вкладка «Подписи»). */
  indent?: boolean;
}) => {
  const { t } = useTranslation("signatureStamper");
  if (note === null) return null;
  const warn = note === "missing";
  return (
    <div
      className="flex"
      style={{
        gap: "0.3125rem",
        alignItems: "flex-start",
        fontSize: "0.65625rem",
        lineHeight: 1.4,
        paddingLeft: indent ? "2.625rem" : undefined,
        color: warn ? "var(--c-warn)" : "var(--fg-2)",
      }}
      role={warn ? "status" : undefined}
      data-testid={`place-anchor-${slotId}`}
      data-note={note}
    >
      <CircleAlert
        size="0.6875rem"
        aria-hidden="true"
        style={{ flexShrink: 0, marginTop: "0.0625rem" }}
      />
      <span>{t(NOTE_KEYS[note])}</span>
    </div>
  );
};
