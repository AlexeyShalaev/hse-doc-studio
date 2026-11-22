import { useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import { resolvePointer } from "./model/pointer";
import { Spinner } from "@shared/ui";
import type { Words } from "../words";
import { ConditionForm } from "./ConditionForm";
import type { ConditionEdit, EditTarget } from "./useConditionEdit";

type EditSectionProps = {
  edit: ConditionEdit;
  targets: readonly EditTarget[];
  /** Сколько условий элемента здесь править нельзя. */
  other: number;
  words: Words;
  names: ReadonlyMap<string, string>;
  /** Сколько правок внесено, пока форма открыта: «Отменить» откатывает их. */
  changed: number;
  onDone: () => void;
  onCancel: () => void;
};

/**
 * Правка условия по месту (pack-studio-ux.md, 5.4, состояние 3): мини-формы записей описания
 * версии, подписанные фразой, с чипами. Каждое изменение сразу пишется в черновик, результат
 * пересчитывается, разницу показывает блок под формой. «Готово» закрывает форму, «Отменить»
 * откатывает то, что внесено с её открытия.
 */
export const EditSection = ({
  edit,
  targets,
  other,
  words,
  names,
  changed,
  onDone,
  onCancel,
}: EditSectionProps) => {
  const { t } = useTranslation("packSpace");
  const root = useRef<HTMLDivElement>(null);
  // Открытая правка забирает фокус: Tab ведёт по полям, а не по тому, что выше.
  useEffect(() => {
    root.current?.focus();
  }, []);
  const locked = edit.blocked !== null || edit.busy;
  return (
    <div
      className="sp-details-form"
      role="group"
      tabIndex={-1}
      ref={root}
      aria-label={t("details.edit.title")}
      data-testid="sp-edit"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onDone();
        }
      }}
    >
      {edit.loadFailed !== null && (
        <p
          className="sp-details-note"
          role="alert"
          data-testid="sp-edit-load-failed"
        >
          {t("details.edit.loadFailed")} {packErrorText(edit.loadFailed)}
        </p>
      )}
      {!edit.ready && edit.loadFailed === null && (
        <p
          className="sp-details-muted"
          role="status"
          data-testid="sp-edit-loading"
        >
          <Spinner size="sm" /> {t("details.edit.loading")}
        </p>
      )}
      {edit.ready &&
        targets.map((target) => {
          const found = resolvePointer(edit.data(target.file), target.pointer);
          if (found === null) {
            return (
              <p
                key={`${target.file}#${target.pointer}`}
                className="sp-details-note"
                role="alert"
              >
                {t("details.edit.missing")}
              </p>
            );
          }
          return (
            <div
              key={`${target.file}#${target.pointer}`}
              className="sp-edit-rule"
            >
              <ConditionForm
                target={target}
                value={found.value}
                context={edit.formContext}
                disabled={locked}
                words={words}
                names={names}
                onChange={(change) => {
                  void edit.change(target, change);
                }}
              />
              {found.exists && (
                <button
                  type="button"
                  className="btn sm ghost"
                  disabled={locked}
                  data-testid="sp-edit-remove"
                  onClick={() => {
                    void edit.remove(target);
                  }}
                >
                  <Trash2 size="0.75rem" aria-hidden="true" />
                  {t("details.edit.remove")}
                </button>
              )}
            </div>
          );
        })}
      {other > 0 && (
        <p className="sp-details-muted" data-testid="sp-edit-other">
          {t("details.edit.other", { count: other })}
        </p>
      )}
      <p className="sp-details-muted">{t("details.edit.saveNote")}</p>
      <div className="sp-details-row">
        <button
          type="button"
          className="btn primary sm"
          data-testid="sp-edit-done"
          onClick={onDone}
        >
          {t("details.edit.done")}
        </button>
        <button
          type="button"
          className="btn sm ghost"
          disabled={changed === 0 || locked}
          data-testid="sp-edit-cancel"
          onClick={onCancel}
        >
          {t("details.edit.cancel")}
        </button>
      </div>
    </div>
  );
};
