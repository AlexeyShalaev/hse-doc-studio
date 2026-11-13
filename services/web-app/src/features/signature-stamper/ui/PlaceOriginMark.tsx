import { useTranslation } from "react-i18next";
import { LayoutTemplate, PencilLine, RotateCcw } from "lucide-react";
import { placeMarkOf } from "@entities/signature";
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
 * место из шаблона». Без места в шаблоне пометки нет.
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
          fromTemplate ? t("place.fromTemplateTitle") : t("place.changedTitle")
        }
      >
        {fromTemplate ? (
          <LayoutTemplate size="0.5625rem" aria-hidden="true" />
        ) : (
          <PencilLine size="0.5625rem" aria-hidden="true" />
        )}
        {fromTemplate ? t("place.fromTemplate") : t("place.changed")}
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
