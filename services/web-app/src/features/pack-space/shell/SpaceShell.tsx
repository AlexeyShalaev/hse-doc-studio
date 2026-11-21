import type { KeyboardEvent, ReactNode } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SpacePhoneContext } from "./phoneContext";
import "./space-shell.css";

export type SpaceShellProps = {
  /** Левая часть верхней полосы. */
  header: ReactNode;
  /** Правая часть верхней полосы: «Изменения» и главная кнопка. */
  actions?: ReactNode;
  /** Вторая полоса: крошки и вкладки. */
  contextBar?: ReactNode;
  /** Левая колонка «что». На телефоне не рисуется: части уходят в центр. */
  nav?: ReactNode;
  /** Полоса над центром. */
  mainTop?: ReactNode;
  main: ReactNode;
  /** Правая колонка «подробности». */
  details?: ReactNode;
  /** Подробности выбраны: на узких экранах панель выезжает поверх (на широких видна всегда). */
  detailsOpen?: boolean;
  /** Панель «Изменения»: занимает место подробностей, на телефоне весь экран. */
  changes?: ReactNode;
  changesOpen?: boolean;
  /** Закрыть выехавшую панель (крестик и Esc). */
  onSideClose?: () => void;
  /** Нижние вкладки, только на телефоне. */
  bottomTabs?: ReactNode;
  /** Телефонная раскладка; по умолчанию решает хост (`useIsPhoneWidth` в `SpaceScreen`). */
  phone?: boolean;
};

/**
 * Каркас экрана пространства (pack-studio-ux.md, 4.5 и 8.6): слоты и раскладка, никаких запросов.
 * Колонки на `@container` (от 1100 px три, уже две и выезжающие подробности), телефон по `phone`.
 */
export const SpaceShell = ({
  header,
  actions,
  contextBar,
  nav,
  mainTop,
  main,
  details,
  detailsOpen = false,
  changes,
  changesOpen = false,
  onSideClose,
  bottomTabs,
  phone = false,
}: SpaceShellProps) => {
  const { t } = useTranslation("packSpace");
  const showChanges = changesOpen && changes !== undefined;
  const side = showChanges ? changes : details;
  const sideOpen = showChanges || detailsOpen;
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && sideOpen) onSideClose?.();
  };
  return (
    <SpacePhoneContext.Provider value={phone}>
      <div
        className="sp-root"
        data-testid="sp-shell"
        data-phone={phone ? "" : undefined}
      >
        <header className="sp-bar" data-testid="sp-bar">
          <div className="sp-bar-lead">{header}</div>
          {actions ? <div className="sp-bar-actions">{actions}</div> : null}
        </header>
        {contextBar ? (
          <div className="sp-context" data-testid="sp-context">
            {contextBar}
          </div>
        ) : null}
        {phone && showChanges ? (
          <div className="sp-page" data-testid="sp-changes-page">
            {changes}
          </div>
        ) : (
          <div className="sp-grid" data-nav={!phone && nav ? "" : undefined}>
            {!phone && nav ? (
              <aside className="sp-nav" data-testid="sp-nav">
                {nav}
              </aside>
            ) : null}
            <section className="sp-center">
              {mainTop ? (
                <div className="sp-main-top" data-testid="sp-main-top">
                  {mainTop}
                </div>
              ) : null}
              <div className="sp-main" data-testid="sp-main">
                {main}
              </div>
            </section>
            {side && phone && sideOpen && !showChanges && onSideClose ? (
              // Затемнение под шторкой: касание вне неё закрывает её (для скринридера есть крестик).
              <div
                className="sp-scrim"
                data-testid="sp-scrim"
                aria-hidden="true"
                onClick={onSideClose}
              />
            ) : null}
            {side ? (
              <aside
                className="sp-side"
                data-testid="sp-side"
                data-open={sideOpen}
                onKeyDown={onKeyDown}
              >
                {!showChanges && onSideClose ? (
                  <div className="sp-side-bar">
                    <span className="sp-side-handle" aria-hidden="true" />
                    <button
                      type="button"
                      className="icon-btn sp-side-close"
                      aria-label={t("shell.close")}
                      title={t("shell.close")}
                      onClick={onSideClose}
                    >
                      <X size="0.9375rem" />
                    </button>
                  </div>
                ) : null}
                {side}
              </aside>
            ) : null}
          </div>
        )}
        {phone && bottomTabs ? (
          <div className="sp-bottom" data-testid="sp-bottom">
            {bottomTabs}
          </div>
        ) : null}
      </div>
    </SpacePhoneContext.Provider>
  );
};
