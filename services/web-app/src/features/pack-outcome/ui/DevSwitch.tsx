import { useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { packOutcomeKeys } from "@entities/pack-studio";
import {
  REFERENCE_BEHAVIORS,
  outcomeReference,
  type ReferenceBehavior,
  type ReferenceSource,
} from "@entities/pack-studio/reference";
import { Select } from "@shared/ui";

/**
 * Переключатель данных результата в разработке: «Эталоны» (ответы из contracts/pack-studio/fixtures)
 * или «Сервер» (запросы уходят настоящему бэкенду), плюс состояния, которые нужно увидеть
 * (пусто, медленно, ошибка). В рабочую сборку не попадает: подключается только под
 * import.meta.env.DEV.
 */
const DevSwitch = ({ workspaceId }: { workspaceId: string }) => {
  const { t } = useTranslation("packOutcome");
  const client = useQueryClient();
  const source = useSyncExternalStore(
    outcomeReference.subscribe,
    outcomeReference.source,
  );
  const behavior = useSyncExternalStore(
    outcomeReference.subscribe,
    outcomeReference.behavior,
  );
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: packOutcomeKeys.all(workspaceId),
    });
  };
  return (
    <div
      className="po-dev"
      role="group"
      aria-label={t("dev.label")}
      data-testid="outcome-dev-switch"
    >
      <Select
        ariaLabel={t("dev.source")}
        value={source}
        options={[
          { value: "reference", label: t("dev.reference") },
          { value: "server", label: t("dev.server") },
        ]}
        onValueChange={(next) => {
          outcomeReference.setSource(next as ReferenceSource);
          refresh();
        }}
      />
      {source === "reference" && (
        <Select
          ariaLabel={t("dev.behavior")}
          value={behavior}
          options={REFERENCE_BEHAVIORS.map((item) => ({
            value: item,
            label: t(`dev.behaviors.${item}`),
          }))}
          onValueChange={(next) => {
            outcomeReference.setBehavior(next as ReferenceBehavior);
            refresh();
          }}
        />
      )}
    </div>
  );
};

export default DevSwitch;
