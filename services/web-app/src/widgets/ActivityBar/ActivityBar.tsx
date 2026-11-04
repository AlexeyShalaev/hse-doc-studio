import {
  Bot,
  FileText,
  Flag,
  FolderTree,
  History,
  type LucideIcon,
  Menu,
  Settings,
  SlidersHorizontal,
  ShieldAlert,
} from "lucide-react";
import { useState } from "react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useIsPhoneWidth, type WorkbenchActivity } from "@shared/lib";
import { Modal } from "@shared/ui";
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
  /** Бейдж «Настроек проекта»: например, вышло обновление шаблона. */
  projectSettingsBadge?: ActivityItemBadge | undefined;
  /** История изменений — полноэкранная страница, боковой панели у неё нет. */
  onOpenVersions: () => void;
  isVersionsActive: boolean;
  /**
   * Бейдж «Истории» от синхронизации (конфликты, нет доступа, новое в
   * репозитории). Важнее счётчика несохранённых файлов и подменяет его.
   */
  versionsBadge?: ActivityItemBadge | undefined;
  /** Подсказка «Истории» вместо обычной, когда есть бейдж синхронизации. */
  versionsTooltip?: string | undefined;
  counts: ActivityBarCounts;
  /** ИИ-агент — тумблер правого дока, как было в нижней части старого борта. */
  isAgentActive: boolean;
  onToggleAgent: () => void;
  /** Настройки приложения: уводят из проекта на отдельную страницу. */
  onOpenSystemSettings: () => void;
  /** Скрытые пункты: проект открыт по ссылке, и право на них сервер не даст. */
  hidden?: readonly ActivityHiddenItem[];
};

export type ActivityHiddenItem =
  "submit" | "projectSettings" | "agent" | "systemSettings";

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
  projectSettingsBadge,
  onOpenVersions,
  isVersionsActive,
  versionsBadge,
  versionsTooltip,
  counts,
  isAgentActive,
  onToggleAgent,
  onOpenSystemSettings,
  hidden = [],
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

  const shown = items.filter(
    (item) => !(item.id === "submit" && hidden.includes("submit")),
  );

  const isPhone = useIsPhoneWidth();
  const [isMoreOpen, setIsMoreOpen] = useState(false);

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

  // Телефон: нижняя панель вкладок. Четыре режима и «Ещё»: настройки проекта, история, агент
  // и настройки системы уходят в шторку, пять-восемь значков в ряд не дали бы зон касания 40 px.
  if (isPhone) {
    const versionsItemBadge =
      versionsBadge ??
      (counts.changedFiles > 0
        ? ({ kind: "count", tone: "info", count: counts.changedFiles } as const)
        : undefined);
    // Бейдж «Ещё» складывается из бейджей спрятанных пунктов: самый тревожный наверх.
    const moreBadge: ActivityItemBadge | undefined =
      [projectSettingsBadge, versionsItemBadge].find(
        (badge) => badge?.kind === "count" && badge.tone === "err",
      ) ??
      projectSettingsBadge ??
      versionsItemBadge;
    const closeAnd = (action: () => void) => () => {
      setIsMoreOpen(false);
      action();
    };
    const moreRows: {
      id: string;
      icon: LucideIcon;
      label: string;
      badge?: ActivityItemBadge | undefined;
      active?: boolean;
      onSelect: () => void;
      hide?: boolean;
    }[] = [
      {
        id: "projectSettings",
        icon: SlidersHorizontal,
        label: t("activity.projectSettings"),
        badge: projectSettingsBadge,
        active: isProjectSettingsActive,
        onSelect: onOpenProjectSettings,
        hide: hidden.includes("projectSettings"),
      },
      {
        id: "versions",
        icon: History,
        label: t("activity.versions"),
        badge: versionsItemBadge,
        active: isVersionsActive,
        onSelect: onOpenVersions,
      },
      {
        id: "agent",
        icon: Bot,
        label: t("activity.agent"),
        active: isAgentActive,
        onSelect: onToggleAgent,
        hide: hidden.includes("agent"),
      },
      {
        id: "systemSettings",
        icon: Settings,
        label: t("activity.systemSettings"),
        onSelect: onOpenSystemSettings,
        hide: hidden.includes("systemSettings"),
      },
    ];
    return (
      <>
        <nav
          className="activity-bar activity-bar--tabs"
          aria-label={t("overview.title")}
        >
          {shown.map(renderActivity)}
          <ActivityItem
            icon={Menu}
            label={t("activity.more")}
            tooltip={t("activity.moreTooltip")}
            isActive={isProjectSettingsActive || isVersionsActive || isMoreOpen}
            badge={moreBadge}
            onSelect={() => {
              setIsMoreOpen(true);
            }}
          />
        </nav>
        <Modal
          isOpen={isMoreOpen}
          onClose={() => {
            setIsMoreOpen(false);
          }}
          title={t("activity.more")}
        >
          <div className="activity-more" data-testid="activity-more">
            {moreRows
              .filter((row) => !row.hide)
              .map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className={clsx(
                    "row-btn activity-more-row",
                    row.active && "active",
                  )}
                  data-testid={`activity-more-${row.id}`}
                  onClick={closeAnd(row.onSelect)}
                >
                  <row.icon size="1.0625rem" aria-hidden />
                  <span className="activity-more-label">{row.label}</span>
                  {row.badge?.kind === "count" && (
                    <span
                      className={clsx("activity-badge inline", row.badge.tone)}
                    >
                      {row.badge.count > 99 ? "99+" : row.badge.count}
                    </span>
                  )}
                </button>
              ))}
          </div>
        </Modal>
      </>
    );
  }

  return (
    <nav className="activity-bar" aria-label={t("overview.title")}>
      {shown.map(renderActivity)}

      {/* Ползунки, а не шестерёнка: шестерёнка закреплена за настройками
          приложения — и внизу рейки, и в титулбаре. Проектные настройки — это
          параметры одной работы, а не системы. */}
      {!hidden.includes("projectSettings") && (
        <ActivityItem
          icon={SlidersHorizontal}
          label={t("activity.projectSettings")}
          tooltip={t("activity.projectSettingsTooltip")}
          isActive={isProjectSettingsActive}
          badge={projectSettingsBadge}
          onSelect={onOpenProjectSettings}
        />
      )}

      {/* История — полноэкранная страница, как и настройки проекта: своей
          боковой панели у неё нет, поэтому она не режим, а переход. */}
      <ActivityItem
        icon={History}
        label={t("activity.versions")}
        tooltip={versionsTooltip ?? t("activity.versionsTooltip")}
        isActive={isVersionsActive}
        badge={
          versionsBadge ??
          (counts.changedFiles > 0
            ? { kind: "count", tone: "info", count: counts.changedFiles }
            : undefined)
        }
        onSelect={onOpenVersions}
      />

      <div className="activity-spacer" />
      <div
        className="divider"
        aria-hidden
        style={{ width: "1.5rem", margin: "0.25rem 0" }}
      />

      {!hidden.includes("agent") && (
        <ActivityItem
          icon={Bot}
          label={t("activity.agent")}
          tooltip={t("activity.agentTooltip")}
          isActive={isAgentActive}
          onSelect={onToggleAgent}
        />
      )}
      {!hidden.includes("systemSettings") && (
        <ActivityItem
          icon={Settings}
          label={t("activity.systemSettings")}
          tooltip={t("activity.systemSettingsTooltip")}
          // Настройки приложения — не режим панели и не канвас проекта: они
          // уводят на /settings, поэтому подсвеченными в рейке не бывают.
          isActive={false}
          onSelect={onOpenSystemSettings}
        />
      )}
    </nav>
  );
};
