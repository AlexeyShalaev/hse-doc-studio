import { RotateCcw, Route } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import {
  missingSlots,
  seedSteps,
  stepsText,
  type Steps,
} from "../lib/routeSteps";
import { BlockHead } from "./kit";
import { StepsEditor } from "./StepsEditor";

export type RouteOrderCardProps = {
  title: string;
  hint: string;
  /** Свой порядок (`signatures.route` или `signing_route`); null: ключа нет. */
  declared: Steps | null;
  /** Что действует без своего порядка: порядок версии или встроенный. */
  inherited: Steps;
  inheritedLabel: string;
  catalog: readonly string[];
  slotLabel: (slot: string) => string;
  disabled: boolean;
  onSave: (steps: Steps | null) => void;
  testId: string;
};

/**
 * Порядок маршрута (5.6): свой (`signatures.route` версии или `signing_route` точки) или
 * унаследованный. Каждая правка сразу пишется в `version.yaml`; «Убрать свой порядок»
 * удаляет ключ, и действует порядок уровнем выше.
 */
export const RouteOrderCard = ({
  title,
  hint,
  declared,
  inherited,
  inheritedLabel,
  catalog,
  slotLabel,
  disabled,
  onSave,
  testId,
}: RouteOrderCardProps) => {
  const { t } = useTranslation("packStudio");
  const missing = declared ? missingSlots(declared, catalog) : [];
  const unknown = declared
    ? declared.flat().filter((slot) => !catalog.includes(slot))
    : [];
  return (
    <section className="psf-block" data-testid={testId}>
      <BlockHead
        title={title}
        hint={hint}
        actions={
          declared === null ? (
            <Button
              size="xs"
              variant="secondary"
              disabled={disabled}
              onClick={() => {
                onSave(seedSteps(inherited, catalog));
              }}
              data-testid={`${testId}-own`}
            >
              <Route size="0.6875rem" />
              {t("submission.route.own")}
            </Button>
          ) : (
            <Button
              size="xs"
              variant="ghost"
              disabled={disabled}
              onClick={() => {
                onSave(null);
              }}
              data-testid={`${testId}-inherit`}
            >
              <RotateCcw size="0.6875rem" />
              {t("submission.route.inherit", { what: inheritedLabel })}
            </Button>
          )
        }
      />
      {declared === null ? (
        <p className="psf-muted" data-testid={`${testId}-inherited`}>
          {t("submission.route.inherited", {
            what: inheritedLabel,
            steps: stepsText(seedSteps(inherited, catalog), slotLabel),
          })}
        </p>
      ) : (
        <>
          <StepsEditor
            steps={declared}
            catalog={catalog}
            slotLabel={slotLabel}
            disabled={disabled}
            onChange={onSave}
            testId={`${testId}-steps`}
          />
          {missing.length > 0 && (
            <p className="hint">
              {t("submission.route.missing", {
                slots: missing.map(slotLabel).join(", "),
              })}
            </p>
          )}
          {unknown.length > 0 && (
            <p className="hint psf-warn">
              {t("submission.route.unknown", { slots: unknown.join(", ") })}
            </p>
          )}
        </>
      )}
    </section>
  );
};
