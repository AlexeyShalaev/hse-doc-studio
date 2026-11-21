import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSpace } from "../context/SpaceContext";
import { DeltaStrip } from "./DeltaStrip";
import { SituationBar } from "./SituationBar";

/**
 * Всё, что область кладёт над центром «Результата»: у выпущенной версии плашка «не меняется»
 * (5.3), затем полоса условий и плашка «что изменилось».
 */
const SituationTop = () => {
  const { t } = useTranslation("packSpace");
  const { released, versionRef } = useSpace();
  return (
    <div className="sp-sit-top">
      {released ? (
        <div className="sp-sit-released" data-testid="sp-sit-released">
          <Lock size="0.9375rem" aria-hidden="true" />
          <p>
            <b>{t("situation.released", { version: versionRef.version })}</b>{" "}
            {t("situation.releasedHint")}
          </p>
        </div>
      ) : null}
      <SituationBar />
      <DeltaStrip />
    </div>
  );
};

export default SituationTop;
