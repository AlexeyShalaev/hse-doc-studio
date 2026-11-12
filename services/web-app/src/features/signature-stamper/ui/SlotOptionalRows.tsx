import { useId } from "react";
import { useTranslation } from "react-i18next";
import { CircleSlash, Undo2 } from "lucide-react";
import { localeTag, pickLocalized } from "@shared/lib";
import type {
  SignatureProfileRef,
  SignaturesStateResponse,
} from "@shared/api/types";

/**
 * «Подпись необязательна» у слота документа (docs/design/signing-route.md, 13.9): строка с
 * галочкой на каждую точку, где слот требуется (`required_by`) или куда его включил маршрут
 * сверх точки (`extra_by`). Отметить нельзя, если пак требует подпись, она уже стоит под
 * маршрутом или нет прав; снять отметку можно всегда, если есть права.
 */
export type SlotOptionalControl = {
  /** Может ли вошедший отмечать: те же, кто отправляет на подписание. */
  canEdit: boolean;
  /** Слот уже подписан в маршруте, который держит документ. */
  isSigned: (slotId: string) => boolean;
  /** Запрос по этой паре ещё идёт. */
  isPending: (slotId: string, profileId: string) => boolean;
  onChange: (slotId: string, profileId: string, optional: boolean) => void;
};

export type SlotOptionalRowsProps = {
  docId: string;
  slot: {
    id: string;
    required?: boolean | undefined;
    required_by?: Record<string, SignatureProfileRef[]> | undefined;
    extra_by?: Record<string, SignatureProfileRef[]> | undefined;
  };
  state: SignaturesStateResponse;
  lang: string;
  control: SlotOptionalControl;
};

const formatDay = (iso: string): string =>
  new Date(iso).toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
  });

export const SlotOptionalRows = ({
  docId,
  slot,
  state,
  lang,
  control,
}: SlotOptionalRowsProps) => {
  const { t } = useTranslation("signatureStamper");
  const baseId = useId();
  const required = slot.required_by?.[docId] ?? [];
  const extra = (slot.extra_by?.[docId] ?? []).filter(
    (point) => !required.some((r) => r.id === point.id),
  );
  const points = [...required, ...extra];
  if (points.length === 0) return null;
  const skip = state.skipped?.[docId]?.[slot.id];

  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.375rem", paddingLeft: "2.625rem" }}
      data-testid={`doc-optional-${slot.id}`}
    >
      {points.map((point) => {
        const checked =
          state.optional?.[docId]?.[point.id]?.includes(slot.id) ?? false;
        const skipped = skip?.profile_id === point.id ? skip : null;
        // Снять отметку можно всегда; отметить только неподписанный слот, который пак не требует.
        const reason = !control.canEdit
          ? t("docPlacement.optional.noRights")
          : checked
            ? null
            : slot.required === true
              ? t("docPlacement.optional.required")
              : control.isSigned(slot.id)
                ? t("docPlacement.optional.signed")
                : null;
        const pending = control.isPending(slot.id, point.id);
        const name = pickLocalized(point.name, lang, point.id);
        const label =
          points.length === 1 && required.length === 1
            ? t("docPlacement.optional.here")
            : t("docPlacement.optional.at", { checkpoint: name });
        const hintId = `${baseId}-${point.id}`;
        const note =
          reason ?? (checked ? t("docPlacement.optional.hint") : null);
        return (
          <div
            key={point.id}
            className="flex flex-col"
            style={{ gap: "0.125rem", fontSize: "0.65625rem" }}
          >
            <label
              className="flex items-center"
              style={{
                gap: "0.375rem",
                cursor: reason === null ? "pointer" : "default",
                color: reason === null ? "var(--fg-1)" : "var(--fg-3)",
              }}
              title={t("docPlacement.optional.hint")}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={reason !== null || pending}
                aria-describedby={note === null ? undefined : hintId}
                data-testid={`doc-optional-${slot.id}-${point.id}`}
                onChange={(e) => {
                  control.onChange(slot.id, point.id, e.target.checked);
                }}
              />
              <span>{label}</span>
            </label>
            {note !== null && (
              <span
                id={hintId}
                className="dim"
                style={{ paddingLeft: "1.25rem", lineHeight: 1.4 }}
              >
                {note}
              </span>
            )}
            {skipped && (
              <span
                className="flex"
                style={{
                  gap: "0.25rem",
                  alignItems: "flex-start",
                  paddingLeft: "1.25rem",
                  color: "var(--fg-2)",
                }}
                data-testid={`doc-skipped-${slot.id}`}
              >
                <CircleSlash
                  size="0.6875rem"
                  aria-hidden="true"
                  style={{
                    flexShrink: 0,
                    alignSelf: "flex-start",
                    marginTop: "0.125rem",
                  }}
                />
                <span>
                  {t("docPlacement.optional.skipped", {
                    date: formatDay(skipped.at),
                  })}
                  {skipped.keep_mark &&
                    ` · ${t("docPlacement.optional.keptMark")}`}
                </span>
              </span>
            )}
            {skipped && !checked && (
              <span
                className="flex"
                style={{
                  gap: "0.25rem",
                  alignItems: "flex-start",
                  paddingLeft: "1.25rem",
                  color: "var(--c-warn)",
                }}
              >
                <Undo2
                  size="0.6875rem"
                  aria-hidden="true"
                  style={{
                    flexShrink: 0,
                    alignSelf: "flex-start",
                    marginTop: "0.125rem",
                  }}
                />
                <span>{t("docPlacement.optional.returns")}</span>
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};
