import { Eye, GitPullRequest, PencilLine, ShieldCheck } from "lucide-react";
import type { ComponentType } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { SPACE_QUERY, SPACE_TABS, type SpaceTab } from "@entities/pack-studio";
import { useChangesStatus } from "../changes/useChangesStatus";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import "./space-phone.css";

const ICON: Record<SpaceTab, ComponentType<{ size?: string }>> = {
  result: Eye,
  content: PencilLine,
  check: ShieldCheck,
};

/**
 * Нижние вкладки телефона (pack-studio-ux.md, 4.5 и 5.8): Результат, Содержимое, Проверка и
 * «Изменения» с числом на значке. «Изменения» открывают страницу (`changes=1`), а не панель; тот же
 * щелчок по открытым «Изменениям» закрывает её. Пока в поле или редакторе фокус (набор текста,
 * экранная клавиатура), вкладки прячет CSS: высота нужна тексту.
 */
export const PhoneTabs = () => {
  const { t } = useTranslation("packSpace");
  const { tab, location } = useSpace();
  const nav = useSpaceNav();
  const { changedFiles } = useChangesStatus();
  const changesOpen =
    new URLSearchParams(location.search).get(SPACE_QUERY.changes) === "1";
  return (
    <nav
      className="sp-ph-tabs"
      aria-label={t("shell.tabsLabel")}
      data-testid="sp-phone-tabs"
    >
      {SPACE_TABS.map((item) => {
        const Icon = ICON[item];
        return (
          <Link
            key={item}
            to={nav.href({ tab: item, changes: false })}
            className="sp-ph-tab"
            aria-current={item === tab && !changesOpen ? "page" : undefined}
            data-testid={`sp-bottom-${item}`}
          >
            <Icon size="1.25rem" />
            <span>{t(`shell.tabs.${item}`)}</span>
          </Link>
        );
      })}
      <Link
        to={nav.href({ changes: !changesOpen })}
        className="sp-ph-tab"
        aria-current={changesOpen ? "page" : undefined}
        aria-label={
          changedFiles > 0
            ? t("changes.button.aria", { count: changedFiles })
            : t("shell.tabs.changes")
        }
        data-testid="sp-bottom-changes"
      >
        <span className="sp-ph-icon">
          <GitPullRequest size="1.25rem" />
          {changedFiles > 0 && (
            <span className="sp-ph-badge" data-testid="sp-bottom-count">
              {changedFiles}
            </span>
          )}
        </span>
        <span>{t("shell.tabs.changes")}</span>
      </Link>
    </nav>
  );
};
