import { Suspense, useEffect, useId, useRef, useState } from "react";
import { Trash2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText, type OutcomeTrace } from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { Spinner } from "@shared/ui";
import { affectedElements } from "../../lib/edit/affected";
import { describeElement } from "../../lib/elements";
import { resolvePointer } from "../../lib/edit/pointer";
import { recordOf, type RuleRecord } from "../../lib/edit/shape";
import { useOutcomeModel } from "../../model";
import { Notice } from "../Notice";
import type { EditNotice, EditTarget } from "./context";
import { useRuleEdit } from "./context";
import { LazyRuleForm } from "./LazyRuleForm";
import "./edit.css";

type RuleEditorProps = {
  trace: OutcomeTrace;
  target: EditTarget;
  onClose: () => void;
};

const reasonOf = (error: unknown): string | null =>
  error instanceof ApiError && typeof error.data?.reason === "string"
    ? error.data.reason
    : null;

/** Плашка отказа записи: чужая правка, неподходящая запись, ошибка схемы. */
export const EditNoticeView = ({
  notice,
  onDismiss,
}: {
  notice: EditNotice;
  onDismiss: () => void;
}) => {
  const { t } = useTranslation("packOutcome");
  const ui = useRuleEdit();
  const dismiss = (
    <button type="button" className="btn sm" onClick={onDismiss}>
      {t("edit.dismiss")}
    </button>
  );
  if (notice.kind === "drift") {
    return (
      <Notice
        tone="error"
        title={t("edit.notice.driftTitle")}
        testId="outcome-edit-notice"
        actions={
          <>
            <button
              type="button"
              className="btn sm"
              data-testid="outcome-edit-force"
              onClick={() => {
                ui?.force(notice.direction);
              }}
            >
              {t(
                notice.direction === "undo"
                  ? "edit.notice.forceUndo"
                  : "edit.notice.forceRedo",
              )}
            </button>
            {dismiss}
          </>
        }
      >
        {t("edit.notice.driftLead")}
      </Notice>
    );
  }
  if (notice.kind === "stale") {
    return (
      <Notice
        tone="error"
        title={t("edit.notice.staleTitle")}
        testId="outcome-edit-notice"
        actions={dismiss}
      >
        {t("edit.notice.staleLead")}
      </Notice>
    );
  }
  if (notice.kind === "missing") {
    return (
      <Notice
        tone="error"
        title={t("edit.notice.missingTitle")}
        testId="outcome-edit-notice"
        actions={dismiss}
      >
        {t("edit.notice.missingLead")}
      </Notice>
    );
  }
  const reason = reasonOf(notice.error);
  return (
    <Notice
      tone="error"
      title={t("edit.notice.errorTitle")}
      testId="outcome-edit-notice"
      actions={dismiss}
    >
      {packErrorText(notice.error)}
      {reason && <span className="po-edit-reason po-mono">{reason}</span>}
    </Notice>
  );
};

/** Подтверждение разрушающего действия: сводка «что изменится» по трассе показанного результата. */
const Confirm = ({
  trace,
  target,
  scope,
  record,
  onCancel,
  onDone,
}: {
  trace: OutcomeTrace;
  target: EditTarget;
  scope: "condition" | "record";
  record: RuleRecord | null;
  onCancel: () => void;
  onDone: () => void;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const ui = useRuleEdit();
  const cancel = useRef<HTMLButtonElement>(null);
  const pointer =
    scope === "record" && record ? record.pointer : target.pointer;
  const affected = affectedElements(shown, target.file, pointer);
  useEffect(() => {
    cancel.current?.focus();
  }, []);
  const names = (affected ?? [])
    .slice(0, 5)
    .map((el) => describeElement(shown, el, i18n.language).title);
  const what =
    scope === "record" && record
      ? t(`edit.record.${record.kind}`)
      : t("edit.record.condition");
  return (
    <div
      className="po-edit-confirm"
      role="alertdialog"
      aria-labelledby={`po-confirm-${trace.id}`}
      data-testid="outcome-edit-confirm"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onCancel();
        }
      }}
    >
      <p className="po-edit-confirm-title" id={`po-confirm-${trace.id}`}>
        {t(
          scope === "record" ? "edit.confirm.record" : "edit.confirm.condition",
          {
            what,
          },
        )}
      </p>
      <p className="po-note" data-testid="outcome-edit-affected">
        {affected === null
          ? t("edit.confirm.noOutcome")
          : affected.length === 0
            ? t("edit.confirm.none")
            : t("edit.confirm.count", { count: affected.length })}
      </p>
      {names.length > 0 && (
        <ul className="po-edit-affected">
          {names.map((name, index) => (
            <li key={`${name}-${String(index)}`}>{name}</li>
          ))}
          {affected !== null && affected.length > names.length && (
            <li className="po-note">
              {t("edit.confirm.more", {
                count: affected.length - names.length,
              })}
            </li>
          )}
        </ul>
      )}
      <p className="po-note">{t("edit.confirm.scope")}</p>
      <div className="po-edit-row">
        <button
          type="button"
          className="btn sm danger"
          data-testid="outcome-edit-confirm-yes"
          disabled={ui?.busy}
          onClick={() => {
            void ui?.remove(target, scope).then((done) => {
              if (done) onDone();
            });
          }}
        >
          {t("edit.confirm.yes")}
        </button>
        <button
          type="button"
          className="btn sm"
          ref={cancel}
          data-testid="outcome-edit-confirm-no"
          onClick={onCancel}
        >
          {t("edit.confirm.no")}
        </button>
      </div>
    </div>
  );
};

/**
 * Мини-форма правила прямо в панели (template-studio-outcome.md, 3.5): видна только эта запись
 * манифеста, поля те же, что у вкладки «Форма». Каждая правка сразу пишется в `version.yaml` или
 * `doc.yaml` точечной правкой с `If-Match`; результат пересчитывается, а что в нём поменялось,
 * показывает полоса над панелью.
 */
export const RuleEditor = ({ trace, target, onClose }: RuleEditorProps) => {
  const { t } = useTranslation("packOutcome");
  const ui = useRuleEdit();
  const uid = useId();
  const group = useRef<HTMLDivElement>(null);
  const [confirm, setConfirm] = useState<"condition" | "record" | null>(null);
  // Открытая правка забирает фокус: Tab ведёт по полям формы, а не по цепочке выше.
  useEffect(() => {
    group.current?.focus();
  }, []);
  if (!ui) return null;
  const data = ui.data(target.file);
  const found =
    data === undefined ? null : resolvePointer(data, target.pointer);
  const record = recordOf(target.pointer);
  const notice = ui.notice?.source === "form" ? ui.notice : null;
  const disabled = ui.blocked !== null || ui.busy;
  const hasValue = found?.exists === true;
  return (
    <div
      className="po-edit"
      role="group"
      ref={group}
      tabIndex={-1}
      aria-labelledby={`${uid}-t`}
      data-testid={`outcome-edit-${trace.id}`}
      onKeyDown={(event) => {
        if (event.key === "Escape" && confirm === null) {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <div className="po-edit-head">
        <h4 className="po-edit-title" id={`${uid}-t`}>
          {t("edit.title")}
        </h4>
        <button
          type="button"
          className="icon-btn sm"
          aria-label={t("edit.close")}
          title={t("edit.close")}
          data-testid={`outcome-edit-${trace.id}-close`}
          onClick={onClose}
        >
          <X size="0.875rem" aria-hidden="true" />
        </button>
      </div>
      {ui.loadFailed !== null && (
        <Notice
          tone="error"
          title={t("edit.loadFailed")}
          testId="outcome-edit-load-failed"
        >
          {packErrorText(ui.loadFailed)}
        </Notice>
      )}
      {!ui.ready && ui.loadFailed === null && (
        <p
          className="po-edit-loading"
          role="status"
          data-testid="outcome-edit-loading"
        >
          <Spinner size="sm" />
          {t("edit.loading")}
        </p>
      )}
      {ui.ready && found === null && (
        <Notice
          tone="error"
          title={t("edit.notice.missingTitle")}
          testId="outcome-edit-missing"
        >
          {t("edit.notice.missingLead")}
        </Notice>
      )}
      {ui.ready && found !== null && (
        <Suspense
          fallback={
            <p className="po-edit-loading" role="status">
              <Spinner size="sm" />
              {t("edit.loading")}
            </p>
          }
        >
          <LazyRuleForm
            shape={target.shape}
            pointer={target.pointer}
            value={found.value}
            context={ui.formContext}
            disabled={disabled}
            testId="outcome-edit-form"
            onChange={(next) => {
              void ui.change(target, next);
            }}
          />
        </Suspense>
      )}
      {notice && <EditNoticeView notice={notice} onDismiss={ui.clearNotice} />}
      {ui.ready && found !== null && confirm === null && (
        <div className="po-edit-row po-edit-destructive">
          {hasValue && (
            <button
              type="button"
              className="btn sm"
              disabled={disabled}
              data-testid={`outcome-edit-${trace.id}-remove`}
              onClick={() => {
                setConfirm("condition");
              }}
            >
              <Trash2 size="0.75rem" aria-hidden="true" />
              {t("edit.removeCondition")}
            </button>
          )}
          {record && (
            <button
              type="button"
              className="btn sm"
              disabled={disabled}
              data-testid={`outcome-edit-${trace.id}-delete`}
              onClick={() => {
                setConfirm("record");
              }}
            >
              <Trash2 size="0.75rem" aria-hidden="true" />
              {t(`edit.delete.${record.kind}`)}
            </button>
          )}
        </div>
      )}
      {confirm !== null && (
        <Confirm
          trace={trace}
          target={target}
          scope={confirm}
          record={record}
          onCancel={() => {
            setConfirm(null);
            group.current?.focus();
          }}
          onDone={() => {
            setConfirm(null);
          }}
        />
      )}
    </div>
  );
};
