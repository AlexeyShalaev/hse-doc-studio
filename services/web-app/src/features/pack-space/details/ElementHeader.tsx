import { Check, CircleOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PackOutcome } from "@entities/pack-studio";
import type { ElementInfo } from "@features/pack-outcome/lib/elements";
import { Badge } from "@shared/ui";
import { isIn, type ElementGroup, type ElementState } from "./elementGroup";

type ElementHeaderProps = {
  id: string;
  info: ElementInfo;
  group: ElementGroup;
  state: ElementState | null;
  outcome: PackOutcome | undefined;
};

/** Заголовок элемента: что это, как называется, входит ли в результат. Без идентификаторов. */
export const ElementHeader = ({
  id,
  info,
  group,
  state,
  outcome,
}: ElementHeaderProps) => {
  const { t } = useTranslation("packSpace");
  const doc =
    info.kind === "document"
      ? outcome?.documents.find((item) => item.id === id)
      : undefined;
  const title =
    info.kind === "route_step"
      ? t("details.stepTitle", { n: info.step ?? 0, point: info.point ?? "" })
      : info.title;
  const inPoint =
    info.point && info.kind !== "point" && info.kind !== "route"
      ? t("details.inPoint", { point: info.point })
      : null;
  return (
    <header className="sp-details-head">
      <span className="sp-details-kicker" data-testid="sp-details-kind">
        {t(`details.kind.${info.kind}`)}
        {inPoint ? ` · ${inPoint}` : ""}
      </span>
      <h3 className="sp-details-title" data-testid="sp-details-title">
        {title}
      </h3>
      <div className="sp-details-badges">
        {state !== null && (
          <Badge
            variant={isIn(state) ? "success" : "warning"}
            data-testid="sp-details-state"
          >
            {isIn(state) ? (
              <Check size="0.75rem" aria-hidden="true" />
            ) : (
              <CircleOff size="0.75rem" aria-hidden="true" />
            )}
            {t(`details.state.${group}.${state}`)}
          </Badge>
        )}
        {doc && <Badge>{t(`details.scope.${doc.scope}`)}</Badge>}
        {doc && !doc.required && <Badge>{t("details.optional")}</Badge>}
      </div>
    </header>
  );
};
