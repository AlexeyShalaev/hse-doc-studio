import { useTranslation } from "react-i18next";
import { usePacksSource } from "../api/systemQueries";

export type TemplateRef = {
  pack_id: string;
  template_id: string;
  version: string;
};

/**
 * Текст «шаблона нет в этой Студии», который не врёт про подключённый каталог.
 *
 * Если каталог шаблонов подключён извне и отстаёт от Студии, а версия вшита в
 * саму Студию, виновата не Студия: текст называет каталог. Если версия
 * известна, сверяем точно; если нет, к прежнему тексту добавляем подсказку
 * про отставший каталог. Без сведений о каталоге остаётся прежний текст.
 */
export const useTemplateMissingText = (
  fallback: string,
  template: TemplateRef | null,
  enabled: boolean,
): string => {
  const { t } = useTranslation("templateUpdate");
  const { data } = usePacksSource(enabled);
  if (!enabled || !data?.lagging || !data.path) return fallback;
  const values = { path: data.path, studio: data.studio_version };
  if (!template) return `${fallback} ${t("packs.lagHint", values)}`;
  const entry = data.templates.find(
    (tpl) =>
      tpl.pack_id === template.pack_id &&
      tpl.template_id === template.template_id,
  );
  return entry?.missing.includes(template.version)
    ? t("packs.stale", { ...values, version: template.version })
    : fallback;
};
