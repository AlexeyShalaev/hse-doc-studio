import { GitPullRequest } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { SPACE_QUERY } from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { useChangesStatus } from "./useChangesStatus";
import "./space-changes.css";

/**
 * Кнопка «Изменения» с числом в полосе пространства (pack-studio-ux.md, 4.4): открывает и
 * закрывает панель (`changes=1` в адресе). Число это файлы, изменённые относительно основной
 * ветки; ноль: без числа. Когда панель закрыли с клавиатуры (фокус остался в ней и пропал вместе
 * с ней), фокус возвращается сюда.
 */
export const ChangesButton = () => {
  const { t } = useTranslation("packSpace");
  const { location } = useSpace();
  const nav = useSpaceNav();
  const { changedFiles } = useChangesStatus();
  const open =
    new URLSearchParams(location.search).get(SPACE_QUERY.changes) === "1";
  const ref = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(open);
  useEffect(() => {
    const active = document.activeElement;
    if (
      wasOpen.current &&
      !open &&
      (active === null || active === document.body)
    ) {
      ref.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  return (
    <button
      ref={ref}
      type="button"
      className="btn sp-ch-btn"
      aria-expanded={open}
      aria-controls="sp-changes-panel"
      aria-label={
        changedFiles > 0
          ? t("changes.button.aria", { count: changedFiles })
          : t("changes.button.label")
      }
      title={t("changes.button.title")}
      onClick={() => {
        nav.go({ changes: !open });
      }}
      data-testid="sp-changes-button"
    >
      <GitPullRequest size="0.9375rem" aria-hidden="true" />
      <span className="sp-ch-btn-label">{t("changes.button.label")}</span>
      {changedFiles > 0 && (
        <span className="sp-ch-count" data-testid="sp-changes-count">
          {changedFiles}
        </span>
      )}
    </button>
  );
};
