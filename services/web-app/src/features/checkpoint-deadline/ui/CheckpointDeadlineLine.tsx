import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarClock, CalendarPlus, Pencil, X } from "lucide-react";
import { useSetCheckpointDeadline } from "@entities/submission";
import { pickLocalized, toast } from "@shared/lib";
import {
  DEADLINE_TONE,
  TONE_COLOR,
  useDeadlineText,
  type PointDeadline,
} from "../lib/useDeadlineText";
import { useDeadlinePromptDismissed } from "../model/dismissed";
import { DeadlineForm } from "./DeadlineForm";

export type CheckpointDeadlineProfile = PointDeadline & {
  id: string;
  deadline_hint: Record<string, string> | null;
};

export type CheckpointDeadlineLineProps = {
  projectId: string;
  profile: CheckpointDeadlineProfile;
  /** Право сдачи (`SUBMISSION_CREATE`): владелец и редактор; локально владелец. */
  canEdit: boolean;
  /** «Сейчас» для текста; по умолчанию время открытия экрана (галерея задаёт своё). */
  now?: number;
};

/**
 * Срок сдачи под названием контрольной точки (docs/design/signing-route.md, 16.2). Срока нет:
 * мягкая строка «Срок сдачи не указан» с подсказкой пака, полем и «Не сейчас», которое прячет её
 * для точки в этом браузере. Срок есть: состояние от сервера, карандаш и «Убрать срок».
 */
export const CheckpointDeadlineLine = ({
  projectId,
  profile,
  canEdit,
  now: fixedNow,
}: CheckpointDeadlineLineProps) => {
  const { t, i18n } = useTranslation("checkpointDeadline");
  const [openedAt] = useState(() => Date.now());
  const now = fixedNow ?? openedAt;
  const text = useDeadlineText();
  const [editing, setEditing] = useState(false);
  const [dismissed, dismiss] = useDeadlinePromptDismissed(
    projectId,
    profile.id,
  );
  const mutation = useSetCheckpointDeadline(projectId);
  const hint =
    profile.deadline_hint === null
      ? ""
      : pickLocalized(profile.deadline_hint, i18n.language, "");

  const save = (deadline: string | null) => {
    mutation.mutate(
      { profileId: profile.id, deadline },
      {
        onSuccess: () => {
          setEditing(false);
          toast.success(
            deadline === null ? t("toast.cleared") : t("toast.set"),
          );
        },
        // Отказ сервера (400 `bad_deadline`, права) показывает тост клиента API по коду.
      },
    );
  };

  const hintLine = hint !== "" && (
    <span
      className="dim"
      style={{ fontSize: "0.71875rem" }}
      data-testid="deadline-hint"
    >
      {hint}
    </span>
  );

  if (editing) {
    return (
      <div
        className="flex flex-col"
        style={{ gap: "0.375rem", marginTop: "0.625rem" }}
        data-testid="checkpoint-deadline"
      >
        {hintLine}
        <DeadlineForm
          initial={profile.deadline}
          submitLabel={
            profile.deadline === null ? t("action.set") : t("form.save")
          }
          dismissLabel={t("form.cancel")}
          busy={mutation.isPending}
          onSubmit={save}
          onDismiss={() => {
            setEditing(false);
          }}
        />
      </div>
    );
  }

  if (profile.deadline === null) {
    if (!canEdit) return null;
    if (dismissed) {
      return (
        <div style={{ marginTop: "0.5rem" }} data-testid="checkpoint-deadline">
          <button
            type="button"
            className="btn xs ghost"
            onClick={() => {
              setEditing(true);
            }}
            data-testid="deadline-open"
          >
            <CalendarPlus size="0.6875rem" aria-hidden="true" />
            {t("action.set")}
          </button>
        </div>
      );
    }
    return (
      <div
        className="flex flex-col"
        style={{
          gap: "0.375rem",
          marginTop: "0.625rem",
          padding: "0.625rem 0.75rem",
          border: "1px dashed var(--border)",
          borderRadius: "0.5rem",
        }}
        data-testid="checkpoint-deadline"
      >
        <span
          className="flex items-center"
          style={{ gap: "0.375rem", fontSize: "0.8125rem" }}
        >
          <CalendarClock
            size="0.8125rem"
            aria-hidden="true"
            style={{ color: "var(--fg-3)", flexShrink: 0 }}
          />
          {t("state.none")}
        </span>
        {hintLine}
        <DeadlineForm
          initial={null}
          submitLabel={t("action.set")}
          dismissLabel={t("action.later")}
          busy={mutation.isPending}
          onSubmit={save}
          onDismiss={dismiss}
        />
      </div>
    );
  }

  const tone = DEADLINE_TONE[profile.deadline_state];
  return (
    <div
      className="flex items-center"
      style={{ gap: "0.375rem", marginTop: "0.5rem", flexWrap: "wrap" }}
      data-testid="checkpoint-deadline"
    >
      <span
        className="flex items-center"
        style={{
          gap: "0.375rem",
          fontSize: "0.8125rem",
          color: TONE_COLOR[tone],
          minWidth: 0,
        }}
        title={t("title")}
        data-testid="deadline-state"
        data-state={profile.deadline_state}
      >
        <CalendarClock
          size="0.8125rem"
          aria-hidden="true"
          style={{ flexShrink: 0 }}
        />
        {text.stateText(profile, now)}
      </span>
      {canEdit && (
        <>
          <button
            type="button"
            className="icon-btn sm tt"
            aria-label={t("action.edit")}
            data-tt={t("action.edit")}
            onClick={() => {
              setEditing(true);
            }}
            data-testid="deadline-edit"
          >
            <Pencil size="0.6875rem" />
          </button>
          <button
            type="button"
            className="btn xs ghost"
            disabled={mutation.isPending}
            onClick={() => {
              save(null);
            }}
            data-testid="deadline-clear"
          >
            <X size="0.6875rem" aria-hidden="true" />
            {t("action.clear")}
          </button>
        </>
      )}
    </div>
  );
};
