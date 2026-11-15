import { useTranslation } from "react-i18next";
import type { PackProfileRoute } from "@entities/pack-studio";
import { Spinner } from "@shared/ui";
import { useWhenText } from "../lib/whenText";

export type RoutePreviewProps = {
  route: PackProfileRoute | undefined;
  loading: boolean;
  /** Профиль есть в файле, но лоадер его не читает: маршрута у него нет. */
  unreadable: boolean;
  slotLabel: (slot: string) => string;
  docName: (doc: string) => string;
};

/**
 * «Маршрут в этой комбинации» (5.6): кто подписывает по шагам на синтетическом проекте
 * переключателей предпросмотра, что шаблон добавил по условию, что условие не пропустило,
 * что автор проекта может добавить сам и какие пункты в этой комбинации не сдаются.
 */
export const RoutePreview = ({
  route,
  loading,
  unreadable,
  slotLabel,
  docName,
}: RoutePreviewProps) => {
  const { t } = useTranslation("packStudio");
  const whenText = useWhenText();
  if (unreadable) {
    return <p className="psf-muted">{t("submission.preview.unreadable")}</p>;
  }
  if (!route) {
    return loading ? (
      <Spinner size="sm" />
    ) : (
      <p className="psf-muted">{t("submission.preview.none")}</p>
    );
  }
  const pair = (doc: string, slot: string) =>
    t("submission.preview.pair", { slot: slotLabel(slot), doc: docName(doc) });
  return (
    <div className="psf-preview" data-testid={`route-preview-${route.id}`}>
      {route.steps.length === 0 ? (
        <p className="psf-muted">{t("submission.preview.noSignatures")}</p>
      ) : (
        <ol className="psf-preview-steps">
          {route.steps.map((step, i) => (
            <li key={step.map((p) => p.persona).join("|")}>
              <span className="psf-step-num">
                {t("submission.route.step", { n: i + 1 })}
              </span>
              {step
                .map((p) =>
                  p.name
                    ? `${t(`submission.role.${p.role}`)} (${p.name})`
                    : t(`submission.role.${p.role}`),
                )
                .join(", ")}
            </li>
          ))}
        </ol>
      )}
      <ul className="psf-preview-notes">
        {route.pairs
          .filter((p) => p.source === "preset")
          .map((p) => (
            <li key={`add-${p.doc_id}-${p.slot_id}-${p.persona}`}>
              {t("submission.preview.added", {
                pair: pair(p.doc_id, p.slot_id),
                when: whenText(p.when),
              })}
            </li>
          ))}
        {route.pairs
          .filter((p) => p.optional)
          .map((p) => (
            <li key={`opt-${p.doc_id}-${p.slot_id}-${p.persona}`}>
              {t("submission.preview.optional", {
                pair: pair(p.doc_id, p.slot_id),
              })}
            </li>
          ))}
        {route.skipped.map((p) => (
          <li
            key={`skip-${p.doc_id}-${p.slot_id}`}
            className="psf-muted"
            data-testid="route-preview-skipped"
          >
            {t("submission.preview.skipped", {
              pair: pair(p.doc_id, p.slot_id),
              when: whenText(p.when),
            })}
          </li>
        ))}
        {route.may_add.length > 0 && (
          <li className="psf-muted">
            {t("submission.preview.mayAdd", {
              pairs: route.may_add
                .map((p) => pair(p.doc_id, p.slot_id))
                .join("; "),
            })}
          </li>
        )}
        {route.items_off.length > 0 && (
          <li className="psf-muted">
            {t("submission.preview.itemsOff", {
              docs: route.items_off.map(docName).join(", "),
            })}
          </li>
        )}
        <li className="psf-muted">
          {t(`submission.preview.order.${route.order_source}`)}
        </li>
      </ul>
    </div>
  );
};
