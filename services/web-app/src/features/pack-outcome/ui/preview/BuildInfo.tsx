import { useTranslation } from "react-i18next";
import type {
  PackPreviewBuild,
  PackPreviewDocument,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib";

/**
 * Что собрано (срез F12): вариант документа, итоговое имя файла, сценарий и вводные сценария из
 * ответа сборки. Имя файла сервер считает той же функцией, что и раздел «Документы».
 */
export const BuildInfo = ({
  build,
  doc,
  scenarioName,
}: {
  build: PackPreviewBuild;
  doc: PackPreviewDocument | null;
  /** Название сценария на языке интерфейса; `null`: файла в списке нет, показываем id. */
  scenarioName: string | null;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const variant =
    build.variant == null
      ? null
      : (doc?.variants?.find((v) => v.id === build.variant) ?? null);
  const scenarioInputs = Object.entries(build.scenario_inputs ?? {}).sort(
    ([a], [b]) => (a < b ? -1 : a > b ? 1 : 0),
  );
  return (
    <dl className="po-preview-info" data-testid="outcome-preview-info">
      {build.variant != null && (
        <>
          <dt>{t("preview.info.variant")}</dt>
          <dd data-testid="outcome-preview-info-variant">
            {variant
              ? pickLocalized(variant.label, i18n.language, variant.id)
              : build.variant}
          </dd>
        </>
      )}
      {build.file_name != null && (
        <>
          <dt>{t("preview.info.file")}</dt>
          <dd className="po-mono" data-testid="outcome-preview-info-file">
            {build.file_name}
          </dd>
        </>
      )}
      <dt>{t("preview.info.example")}</dt>
      <dd className="po-mono" data-testid="outcome-preview-info-example">
        {build.example}
      </dd>
      {build.scenario != null && (
        <>
          <dt>{t("preview.info.scenario")}</dt>
          <dd data-testid="outcome-preview-info-scenario">
            {scenarioName ?? build.scenario}
          </dd>
          <dt>{t("preview.info.scenarioInputs")}</dt>
          <dd data-testid="outcome-preview-info-inputs">
            {scenarioInputs.length === 0 ? (
              t("preview.info.noInputs")
            ) : (
              <ul className="po-preview-inputs">
                {scenarioInputs.map(([key, value]) => (
                  <li key={key} className="po-mono">
                    {key}: {value}
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </>
      )}
    </dl>
  );
};
