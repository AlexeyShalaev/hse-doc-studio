import {
  Bot,
  FileText,
  Flag,
  FolderTree,
  History,
  type LucideIcon,
  Settings,
  SlidersHorizontal,
  ShieldAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { WorkbenchActivity } from "@shared/lib";
import { ActivityItem } from "./ActivityItem";
import type { ActivityBadgeTone, ActivityItemBadge } from "./ActivityItem";

// Пять режимов верстака объявлены в workspaceStore: стор — слой shared и не
// имеет права импортировать виджет, поэтому источник истины там, а бар лишь
// реэкспортирует тип через свой public API. «Настройки проекта» в него не
// входят: они открывают канвас во всю ширину, своей панели у них нет — и,
// значит, нет состояния, которое оболочка обязана помнить наравне с режимами.
export type { WorkbenchActivity };

// Счётчики считает оболочка: бар — чистая презентация и ничего не грузит.
export type ActivityBarCounts = {
  // Σ doc.errors по проекту.
  errors: number;
  // Σ doc.warnings по проекту.
  warnings: number;
  // Хоть один поток компиляции этого проекта жив.
  isBuilding: boolean;
  submitBlockers: number;
  changedFiles: number;
};

export type ActivityBarProps = {
  activity: WorkbenchActivity;
  onSelectActivity: (activity: WorkbenchActivity) => void;
  onOpenProjectSettings: () => void;
  isProjectSettingsActive: boolean;
  /** История изменений — полноэкранная страница, боковой панели у неё нет. */
  onOpenVersions: () => void;
  isVersionsActive: boolean;
  counts: ActivityBarCounts;
  /** ИИ-агент — тумблер правого дока, как было в нижней части старого борта. */
  isAgentActive: boolean;
  onToggleAgent: () => void;
  /** Настройки приложения: уводят из проекта на отдельную страницу. */
  onOpenSystemSettings: () => void;
};

type ActivityDescriptor = {
  id: WorkbenchActivity;
  icon: LucideIcon;
  label: string;
  tooltip: string;
  badge: ActivityItemBadge | undefined;
};

const countBadge = (
  tone: ActivityBadgeTone,
  count: number,
): ActivityItemBadge | undefined =>
  count > 0 ? { kind: "count", tone, count } : undefined;

// Ошибки перекрывают предупреждения: два числа на 48-пиксельной кнопке не
// помещаются, а чинить всё равно начинают с ошибок.
const issueBadge = (
  errors: number,
  warnings: number,
): ActivityItemBadge | undefined =>
  countBadge("err", errors) ?? countBadge("warn", warnings);

export const ActivityBar = ({
  activity,
  onSelectActivity,
  onOpenProjectSettings,
  isProjectSettingsActive,
  onOpenVersions,
  isVersionsActive,
  counts,
  isAgentActive,
  onToggleAgent,
  onOpenSystemSettings,
}: ActivityBarProps): React.JSX.Element => {
  const { t } = useTranslation("workbench");

  // Пока идёт сборка, счётчик проблем заведомо неактуален (документы как раз
  // пересобираются), поэтому на «Документах» его вытесняет пульсирующая точка.
  const documentsBadge: ActivityItemBadge | undefined = counts.isBuilding
    ? { kind: "live", label: t("activity.buildingBadge") }
    : issueBadge(counts.errors, counts.warnings);

  const items: ActivityDescriptor[] = [
    {
      id: "documents",
      icon: FileText,
      label: t("activity.documents"),
      tooltip: t("activity.documentsTooltip"),
      badge: documentsBadge,
    },
    {
      id: "review",
      icon: ShieldAlert,
      label: t("activity.review"),
      tooltip: t("activity.reviewTooltip"),
      badge: issueBadge(counts.errors, counts.warnings),
    },
    {
      id: "submit",
      icon: Flag,
      label: t("activity.submit"),
      tooltip: t("activity.submitTooltip"),
      badge: countBadge("warn", counts.submitBlockers),
    },
    {
      id: "files",
      icon: FolderTree,
      label: t("activity.files"),
      tooltip: t("activity.filesTooltip"),
      // Дерево файлов ничего не «требует» — бейдж здесь был бы шумом.
      badge: undefined,
    },
  ];

  const renderActivity = (item: ActivityDescriptor) => (
    <ActivityItem
      key={item.id}
      icon={item.icon}
      label={item.label}
      tooltip={item.tooltip}
      // Пока открыта полноэкранная страница (настройки проекта или история),
      // подсветка режима гаснет. Эти две кнопки — переходы, а не режимы, и их
      // активность считается по адресу, а не по состоянию панели; без этой
      // оговорки «Файлы» и «Настройки» горели одновременно, а два выбранных
      // пункта в одном столбце читаются как сбой.
      isActive={
        item.id === activity && !isProjectSettingsActive && !isVersionsActive
      }
      badge={item.badge}
      onSelect={() => {
        onSelectActivity(item.id);
      }}
    />
  );

  return (
    <nav className="activity-bar" aria-label={t("overview.title")}>
      {items.map(renderActivity)}

      {/* Ползунки, а не шестерёнка: шестерёнка закреплена за настройками
          приложения — и внизу рейки, и в титулбаре. Проектные настройки — это
          параметры одной работы, а не системы. */}
      <ActivityItem
        icon={SlidersHorizontal}
        label={t("activity.projectSettings")}
        tooltip={t("activity.projectSettingsTooltip")}
        isActive={isProjectSettingsActive}
        onSelect={onOpenProjectSettings}
      />

      {/* История — полноэкранная страница, как и настройки проекта: своей
          боковой панели у неё нет, поэтому она не режим, а переход. */}
      <ActivityItem
        icon={History}
        label={t("activity.versions")}
        tooltip={t("activity.versionsTooltip")}
        isActive={isVersionsActive}
        badge={
          counts.changedFiles > 0
            ? { kind: "count", tone: "info", count: counts.changedFiles }
            : undefined
        }
        onSelect={onOpenVersions}
      />

      <div className="activity-spacer" />
      <div
        className="divider"
        aria-hidden
        style={{ width: 24, margin: "4px 0" }}
      />

      <ActivityItem
        icon={Bot}
        label={t("activity.agent")}
        tooltip={t("activity.agentTooltip")}
        isActive={isAgentActive}
        onSelect={onToggleAgent}
      />
      <ActivityItem
        icon={Settings}
        label={t("activity.systemSettings")}
        tooltip={t("activity.systemSettingsTooltip")}
        // Настройки приложения — не режим панели и не канвас проекта: они
        // уводят на /settings, поэтому подсвеченными в рейке не бывают.
        isActive={false}
        onSelect={onOpenSystemSettings}
      />
    </nav>
  );
};
