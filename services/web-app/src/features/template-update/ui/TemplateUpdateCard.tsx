import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpCircle, Sparkles } from "lucide-react";
import { useTemplateUpdateStatus } from "@entities/template-update";
import { TemplateUpdateDialog } from "./TemplateUpdateDialog";
import { dismiss, isDismissed, notesOf } from "./templateUpdate.model";

export type TemplateUpdateCardProps = {
  projectId: string;
};

/**
 * Предложение исправлений шаблона на обзоре проекта.
 *
 * Сам приходит только patch: исправления без новых требований. Новое (minor)
 * и новая редакция (major) живут в настройках проекта и требуют явного шага —
 * требования посреди года не должны меняться под студентом.
 */
export const TemplateUpdateCard = ({ projectId }: TemplateUpdateCardProps) => {
  const { t, i18n } = useTranslation("templateUpdate");
  const { data } = useTemplateUpdateStatus(projectId);
  const [isOpen, setIsOpen] = useState(false);
  const [, setDismissedTick] = useState(0);

  const update = data?.recommended;
  if (
    !data ||
    update?.update_class !== "patch" ||
    data.in_progress ||
    isDismissed(projectId, update.version.version)
  ) {
    return null;
  }
  const notes = notesOf(update, i18n.language);

  return (
    <div
      className="card"
      style={{
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.625rem",
        borderColor: "color-mix(in oklch, var(--accent) 40%, var(--border))",
        maxWidth: "53.75rem",
      }}
    >
      <div className="flex items-center" style={{ gap: "0.5rem" }}>
        <Sparkles size="0.875rem" style={{ color: "var(--accent)" }} />
        <strong style={{ fontSize: "0.8125rem" }}>{t("card.title")}</strong>
      </div>
      <span style={{ fontSize: "0.78125rem" }}>
        {t("card.text", { version: update.version.version })}
      </span>
      {notes.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: "1.125rem", fontSize: "0.75rem" }}>
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <div className="flex" style={{ gap: "0.5rem" }}>
        <button
          type="button"
          className="btn primary"
          onClick={() => {
            setIsOpen(true);
          }}
        >
          <ArrowUpCircle size="0.8125rem" />
          {t("card.review")}
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => {
            dismiss(projectId, update.version.version);
            setDismissedTick((n) => n + 1);
          }}
        >
          {t("card.dismiss")}
        </button>
      </div>
      <TemplateUpdateDialog
        projectId={projectId}
        update={isOpen ? update : null}
        onClose={() => {
          setIsOpen(false);
        }}
      />
    </div>
  );
};
