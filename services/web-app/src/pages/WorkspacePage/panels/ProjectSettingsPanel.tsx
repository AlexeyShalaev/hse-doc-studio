import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { useDocuments } from "@entities/document";
import { useProject } from "@entities/project";
import { useVersionDetail } from "@entities/template-catalog";
import {
  buildMetaGroupCards,
  collectMetaFields,
  collectVariantRows,
  filterMetaFieldsBySection,
  visibleProjectSettingsGroups,
  resolveProjectSettingsGroup,
} from "./project-settings";
import type {
  ProjectSettingsGroupId,
  ProjectSettingsSectionId,
} from "./project-settings";

export type ProjectSettingsPanelProps = {
  projectId: string;
  /** Сырой параметр маршрута — разбирается через resolveProjectSettingsGroup. */
  activeSection: string;
  /**
   * Переход по навигации. Принимает и id группы, и id раздела: маршрут
   * понимает оба, поэтому ссылка на конкретный раздел остаётся рабочей.
   */
  onSelectSection: (
    target: ProjectSettingsGroupId | ProjectSettingsSectionId,
  ) => void;
};

/**
 * Оглавление настроек проекта в сменной панели верстака.
 *
 * Панель ничего не редактирует: она читает те же чистые производные
 * (`sectionData`), что и карточки, поэтому список секций и содержимое канваса
 * не могут разойтись. Активная секция приходит из адреса, активный блок
 * «Метаданных» — из состояния страницы (владелец черновика обязан остаться
 * один, см. ProjectSettingsView).
 */
export const ProjectSettingsPanel = ({
  projectId,
  activeSection,
  onSelectSection,
}: ProjectSettingsPanelProps) => {
  const { t } = useTranslation("workbench");

  const { data: project } = useProject(projectId);
  const { data: versionDetail } = useVersionDetail(
    project?.lock.pack_id ?? "",
    project?.lock.template_id ?? "",
    project?.lock.version ?? "",
  );
  const { data: projectDocuments } = useDocuments(projectId);

  const isTeam = project?.staffing === "team";
  const allMetaFields = collectMetaFields(versionDetail, project?.kind);
  const metaGroups = versionDetail?.meta_groups ?? [];
  const variantRows = collectVariantRows(
    versionDetail,
    projectDocuments,
    project?.lang,
  );

  // Навигация по ГРУППАМ, а не по десяти разделам: искать нужный пункт среди
  // десяти не легче, чем скроллить простыню. Группа — одна страница с одной-
  // тремя карточками.
  const sectionCtx = {
    isTeam,
    hasDocFormats: variantRows.length > 0,
    hasDocSetMeta:
      buildMetaGroupCards(allMetaFields, metaGroups, "documents").length > 0,
    hasMetaFields:
      filterMetaFieldsBySection(allMetaFields, metaGroups, "meta").length > 0,
  };
  const groups = visibleProjectSettingsGroups(sectionCtx);
  const activeGroup = resolveProjectSettingsGroup(activeSection, sectionCtx);

  return (
    <div className="workbench-panel">
      <div className="panel-head">
        <span className="panel-head-title">
          {t("projectSettingsNav.title")}
        </span>
      </div>

      <div className="panel-body">
        <nav aria-label={t("projectSettingsNav.title")}>
          {groups.map((group) => {
            const Icon = group.icon;
            const isActive = group.id === activeGroup.id;
            return (
              <button
                key={group.id}
                type="button"
                className={clsx("row-btn", isActive && "active")}
                // "location", а не "page": страницу в рейке уже помечает
                // кнопка «Настройки», и второй "page" сбил бы скринридер.
                aria-current={isActive ? "location" : undefined}
                onClick={() => {
                  onSelectSection(group.id);
                }}
              >
                <Icon size={13} style={{ flexShrink: 0 }} />
                <span className="truncate" style={{ minWidth: 0 }}>
                  {t(group.labelKey)}
                </span>
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
};
