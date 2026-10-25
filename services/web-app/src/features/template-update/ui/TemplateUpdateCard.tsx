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
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        borderColor: "color-mix(in oklch, var(--accent) 40%, var(--border))",
        maxWidth: 860,
      }}
    >
      <div className="flex items-center" style={{ gap: 8 }}>
        <Sparkles size={14} style={{ color: "var(--accent)" }} />
        <strong style={{ fontSize: 13 }}>{t("card.title")}</strong>
      </div>
      <span style={{ fontSize: 12.5 }}>
        {t("card.text", { version: update.version.version })}
      </span>
      {notes.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <div className="flex" style={{ gap: 8 }}>
        <button
          type="button"
          className="btn primary"
          onClick={() => {
            setIsOpen(true);
          }}
        >
          <ArrowUpCircle size={13} />
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
