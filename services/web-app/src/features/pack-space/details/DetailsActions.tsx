import { Code2, Copy, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { packErrorText, type OutcomeElementRef } from "@entities/pack-studio";
import { Spinner } from "@shared/ui";
import type { SpaceNavPatch } from "../context/nav";
import { useSpaceNav } from "../context/useSpaceNav";
import { useCopyVersion } from "../next-step/useCopyVersion";

/** Куда ведёт «Текст документа» и его родня: часть «Содержимого», где живёт этот элемент. */
export const contentPatch = (
  element: OutcomeElementRef,
): { patch: SpaceNavPatch; label: string } | null => {
  switch (element.section) {
    case "documents":
      return {
        patch: { tab: "content", doc: element.id },
        label: "details.open.document",
      };
    case "meta":
      return {
        patch: { tab: "content", part: "fields" },
        label: "details.open.fields",
      };
    case "forms":
      return {
        patch: { tab: "content", part: "forms" },
        label: "details.open.forms",
      };
    case "points":
      return {
        patch: { tab: "content", part: "deadlines" },
        label: "details.open.deadlines",
      };
    case "route":
      return {
        patch: { tab: "content", part: "signatures" },
        label: "details.open.signatures",
      };
    case "participants":
    case "checks":
      return null;
  }
};

type DetailsActionsProps = {
  element: OutcomeElementRef;
  /** Версия выпущена: вместо «Изменить условия» кнопка «Править копию». */
  released: boolean;
  /** Правка запрещена по другой причине (выпуск реестра). */
  registry: boolean;
  /** Есть что править по месту; `null`: ответ ещё не пришёл. */
  editable: boolean | null;
  editing: boolean;
  onEdit: () => void;
};

/** Кнопки панели: главная («Изменить условия» или «Править копию») и переход в «Содержимое». */
export const DetailsActions = ({
  element,
  released,
  registry,
  editable,
  editing,
  onEdit,
}: DetailsActionsProps) => {
  const { t } = useTranslation("packSpace");
  const nav = useSpaceNav();
  const copy = useCopyVersion();
  const open = contentPatch(element);
  return (
    <div className="sp-details-actions" data-testid="sp-details-actions">
      {released ? (
        <>
          <div className="sp-details-row">
            {/* Главная кнопка «Править копию» уже в полосе пространства (P1): здесь вторичная. */}
            <button
              type="button"
              className="btn"
              disabled={copy.pending}
              data-testid="sp-make-copy"
              onClick={() => void copy.run()}
            >
              {copy.pending ? (
                <Spinner size="sm" />
              ) : (
                <Copy size="0.875rem" aria-hidden="true" />
              )}
              {t("details.makeCopy")}
            </button>
            {open && (
              <Link
                className="btn"
                to={nav.href(open.patch)}
                data-testid="sp-open-content"
              >
                <Code2 size="0.875rem" aria-hidden="true" />
                {t(open.label)}
              </Link>
            )}
          </div>
          {copy.error !== null && (
            <p className="sp-details-note" role="alert">
              {packErrorText(copy.error)}
            </p>
          )}
        </>
      ) : (
        <>
          {registry && (
            <p className="sp-details-muted">{t("details.registry")}</p>
          )}
          <div className="sp-details-row">
            {!editing && (
              <button
                type="button"
                className="btn primary"
                disabled={registry || editable !== true}
                data-testid="sp-edit-open"
                onClick={onEdit}
              >
                <Pencil size="0.875rem" aria-hidden="true" />
                {t("details.edit.open")}
              </button>
            )}
            {open && (
              <Link
                className="btn"
                to={nav.href(open.patch)}
                data-testid="sp-open-content"
              >
                <Code2 size="0.875rem" aria-hidden="true" />
                {t(open.label)}
              </Link>
            )}
          </div>
          {editable === false && (
            <p className="sp-details-muted" data-testid="sp-edit-none">
              {t("details.edit.none")}
            </p>
          )}
        </>
      )}
    </div>
  );
};
