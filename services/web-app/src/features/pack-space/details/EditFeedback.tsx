import { Redo2, Undo2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import type { RuleEdit } from "@features/pack-outcome/lib/edit/plan";
import { tallyDelta } from "@features/pack-outcome/lib/edit/delta";
import type { ConditionEdit } from "./edit/useConditionEdit";

/** Сколько изменившихся строк видно сразу. */
const SHOWN = 6;

/** Одно слово о том, что сделано с условием: «Условие изменено» (без внутренних имён правил). */
const useEntryText = () => {
  const { t } = useTranslation("packSpace");
  return (edit: RuleEdit): string =>
    t(`details.edit.entry.${edit.action}`, {
      what: t(`details.edit.what.${edit.subject}`, {
        defaultValue: t("details.edit.what.other"),
      }),
    });
};

/** Отказ записи: чужая правка, записи больше нет, ошибка, откат поверх чужих изменений. */
const Notice = ({ edit }: { edit: ConditionEdit }) => {
  const { t } = useTranslation("packSpace");
  const { notice } = edit;
  if (!notice) return null;
  const dismiss = (
    <button type="button" className="btn sm" onClick={edit.clearNotice}>
      {t("details.edit.dismiss")}
    </button>
  );
  return (
    <div className="sp-details-note" role="alert" data-testid="sp-edit-notice">
      <p>
        <b>{t(`details.edit.notice.${notice.kind}Title`)}</b>
      </p>
      <p>
        {notice.kind === "error"
          ? packErrorText(notice.error)
          : t(`details.edit.notice.${notice.kind}Lead`)}
      </p>
      <div className="sp-details-row">
        {notice.kind === "drift" && (
          <button
            type="button"
            className="btn sm"
            data-testid="sp-edit-force"
            onClick={() => {
              edit.force(notice.direction);
            }}
          >
            {t(
              notice.direction === "undo"
                ? "details.edit.notice.forceUndo"
                : "details.edit.notice.forceRedo",
            )}
          </button>
        )}
        {dismiss}
      </div>
    </div>
  );
};

/**
 * Что изменилось от правки: плашка «Результат изменился» с тем, что появилось, изменилось и
 * исчезло, плюс отказы записи. Та же запись (`useEditFeed`) годится центру для подсветки строк.
 */
export const EditDelta = ({ edit }: { edit: ConditionEdit }) => {
  const { t } = useTranslation("packSpace");
  const { delta } = edit;
  if (!delta && !edit.notice) return null;
  const tally = delta ? tallyDelta(delta.items) : null;
  return (
    <div className="sp-details-feedback">
      <Notice edit={edit} />
      {delta && (
        <section
          className="sp-details-delta"
          aria-label={t("details.edit.delta.label")}
          data-testid="sp-edit-delta"
        >
          <div className="sp-details-row">
            <b className="sp-details-grow">
              {delta.items.length === 0
                ? t("details.edit.delta.same")
                : t(`details.edit.delta.${delta.direction}`)}
            </b>
            <button
              type="button"
              className="icon-btn sm"
              aria-label={t("details.edit.delta.dismiss")}
              title={t("details.edit.delta.dismiss")}
              data-testid="sp-edit-delta-dismiss"
              onClick={edit.dismissDelta}
            >
              <X size="0.875rem" aria-hidden="true" />
            </button>
          </div>
          {tally && delta.items.length > 0 && (
            <p className="sp-details-muted" data-testid="sp-edit-delta-tally">
              {t("details.edit.delta.tally", tally)}
            </p>
          )}
          <ul className="sp-delta-list">
            {delta.items.slice(0, SHOWN).map((item) => (
              <li
                key={`${item.section}:${item.id}`}
                data-symbol={item.symbol}
                data-testid="sp-edit-delta-item"
              >
                <span className="sp-delta-word">
                  {t(`details.edit.delta.symbol.${item.symbol}`)}
                </span>
                {item.label}
              </li>
            ))}
            {delta.items.length > SHOWN && (
              <li className="sp-details-muted">
                {t("details.edit.delta.more", {
                  count: delta.items.length - SHOWN,
                })}
              </li>
            )}
          </ul>
        </section>
      )}
    </div>
  );
};

/** История правок этой версии: что сделано, что отменено, «Отменить» и «Повторить». */
export const EditHistory = ({ edit }: { edit: ConditionEdit }) => {
  const { t, i18n } = useTranslation("packSpace");
  const text = useEntryText();
  const { history } = edit;
  const locked = edit.blocked !== null || edit.busy;
  return (
    <section
      className="sp-details-block"
      aria-labelledby="sp-history-title"
      data-testid="sp-history"
    >
      <h4 className="sp-details-sub" id="sp-history-title">
        {t("details.edit.history.title", { count: history.entries.length })}
      </h4>
      <div className="sp-details-row">
        <button
          type="button"
          className="btn sm"
          disabled={!edit.canUndo || locked}
          title={t("details.edit.undoHint")}
          data-testid="sp-history-undo"
          onClick={edit.undo}
        >
          <Undo2 size="0.875rem" aria-hidden="true" />
          {t("details.edit.undo")}
        </button>
        <button
          type="button"
          className="btn sm"
          disabled={!edit.canRedo || locked}
          title={t("details.edit.redoHint")}
          data-testid="sp-history-redo"
          onClick={edit.redo}
        >
          <Redo2 size="0.875rem" aria-hidden="true" />
          {t("details.edit.redo")}
        </button>
      </div>
      {history.entries.length === 0 ? (
        <p className="sp-details-muted">{t("details.edit.history.empty")}</p>
      ) : (
        <ol className="sp-history">
          {history.entries.map((entry, index) => (
            <li
              key={entry.id}
              data-state={index < history.cursor ? "applied" : "undone"}
            >
              <time dateTime={new Date(entry.at).toISOString()}>
                {new Date(entry.at).toLocaleTimeString(i18n.language, {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>{" "}
              {text(entry)}{" "}
              <span className="sp-details-muted">
                {t(
                  index < history.cursor
                    ? "details.edit.history.applied"
                    : "details.edit.history.undone",
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
};
