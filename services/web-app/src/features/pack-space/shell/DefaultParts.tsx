import {
  Eye,
  GitPullRequest,
  PencilLine,
  ShieldCheck,
  ArrowLeft,
} from "lucide-react";
import type { ComponentType } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  PACK_STUDIO_PATH,
  SPACE_TABS,
  type SpaceTab,
} from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";

// Запасные части каркаса: работают, пока области не положили в слоты свои. Срез S2 заменяет
// `header` и `contextBar`, S11 `bottomTabs`, области `main` кладут вместо заглушки.

const TAB_ICON: Record<SpaceTab, ComponentType<{ size?: string }>> = {
  result: Eye,
  content: PencilLine,
  check: ShieldCheck,
};

/** Назад к списку и название пространства. */
export const DefaultHeader = () => {
  const { t } = useTranslation("packSpace");
  const { workspace } = useSpace();
  return (
    <>
      <Link
        to={PACK_STUDIO_PATH}
        className="icon-btn"
        aria-label={t("shell.back")}
        title={t("shell.back")}
        data-testid="sp-back"
      >
        <ArrowLeft size="0.9375rem" />
      </Link>
      <h1 className="sp-ws-name truncate" data-testid="sp-ws-name">
        {workspace.label}
      </h1>
    </>
  );
};

/** Три вкладки: Результат, Содержимое, Проверка. Переключение меняет адрес. */
export const SpaceTabs = () => {
  const { t } = useTranslation("packSpace");
  const { tab } = useSpace();
  const nav = useSpaceNav();
  return (
    <nav className="sp-tabs" aria-label={t("shell.tabsLabel")}>
      {SPACE_TABS.map((item) => (
        <Link
          key={item}
          to={nav.href({ tab: item })}
          className="sp-tab"
          aria-current={item === tab ? "page" : undefined}
          data-testid={`sp-tab-${item}`}
        >
          {t(`shell.tabs.${item}`)}
        </Link>
      ))}
    </nav>
  );
};

/** Нижние вкладки телефона: три вкладки и «Изменения» (открывает панель). */
export const DefaultBottomTabs = () => {
  const { t } = useTranslation("packSpace");
  const { tab, location } = useSpace();
  const nav = useSpaceNav();
  const changesOpen =
    new URLSearchParams(location.search).get("changes") === "1";
  return (
    <nav className="sp-bottom-tabs" aria-label={t("shell.tabsLabel")}>
      {SPACE_TABS.map((item) => {
        const Icon = TAB_ICON[item];
        return (
          <Link
            key={item}
            to={nav.href({ tab: item, changes: false })}
            aria-current={item === tab && !changesOpen ? "page" : undefined}
            data-testid={`sp-bottom-${item}`}
          >
            <Icon size="1.125rem" />
            {t(`shell.tabs.${item}`)}
          </Link>
        );
      })}
      <Link
        to={nav.href({ changes: !changesOpen })}
        aria-current={changesOpen ? "page" : undefined}
        data-testid="sp-bottom-changes"
      >
        <GitPullRequest size="1.125rem" />
        {t("shell.tabs.changes")}
      </Link>
    </nav>
  );
};

/** Заглушка центра, пока область не положила свой `main`. */
export const ComingSoon = () => {
  const { t } = useTranslation("packSpace");
  const { tab } = useSpace();
  return (
    <div className="sp-soon" data-testid="sp-soon">
      <h2>{t(`shell.tabs.${tab}`)}</h2>
      <p>{t("shell.soon")}</p>
    </div>
  );
};
