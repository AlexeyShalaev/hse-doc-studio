import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { pickLocalized } from "@shared/lib";
import type { SigningTask } from "@entities/signing-route";
import { formatDay } from "../lib/format";
import { isOverdue } from "../lib/signingState";

/** Шапка: проект, точка сдачи, кто просит, когда отправлено, срок и сообщение автора. */
export const SigningHeader = ({
  task,
  now,
  hideMessage = false,
}: {
  task: SigningTask;
  now: number;
  /** Сообщение показывает плашка «Новая версия» (раздел 12.2). */
  hideMessage?: boolean;
}) => {
  const { t, i18n } = useTranslation("signing");
  const { route } = task;
  const overdue = isOverdue(task, now);
  return (
    <header className="sgn-head" data-testid="signing-head">
      <div className="sgn-eyebrow">
        <span>{route.project.name}</span>
        <Link to={`/projects/${encodeURIComponent(route.project.id)}`}>
          {t("head.openProject")}
        </Link>
      </div>
      <h1 className="sgn-title">
        {pickLocalized(route.profile.name, i18n.language, route.profile.id)}
      </h1>
      <p className="sgn-meta">
        {route.sender && <span>{t("head.from", { name: route.sender })}</span>}
        {route.sent_at && (
          <span>{t("head.sentAt", { date: formatDay(route.sent_at) })}</span>
        )}
        {route.deadline && (
          <span data-overdue={overdue} data-testid="signing-deadline">
            {t(overdue ? "head.overdue" : "head.deadline", {
              date: formatDay(route.deadline),
            })}
          </span>
        )}
      </p>
      {route.message && !hideMessage && (
        <blockquote
          className="sgn-message"
          aria-label={t("head.message")}
          data-testid="signing-message"
        >
          {route.message}
        </blockquote>
      )}
    </header>
  );
};
