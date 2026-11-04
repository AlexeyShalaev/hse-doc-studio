import { useState } from "react";
import { ArrowLeft, Home, LockKeyhole, Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Modal, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type RequestAccessProps = {
  pending: boolean;
  sent: boolean;
  failed: boolean;
  onSend: (message: string | null) => void;
};

export type ProjectUnavailableViewProps = {
  onHome: () => void;
  onBack: () => void;
  /** Вошедшему: «Запросить доступ» (10.10). Ответ сервера одинаков, есть проект или нет. */
  requestAccess?: RequestAccessProps;
};

/**
 * «Проект не найден или у вас нет доступа»: сервер отвечает одинаково на чужой и
 * на несуществующий проект, поэтому страница не называет причину.
 */
export const ProjectUnavailableView = ({
  onHome,
  onBack,
  requestAccess,
}: ProjectUnavailableViewProps) => {
  const { t } = useTranslation("projectAccess");
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  return (
    <main
      className="flex flex-1 items-center justify-center"
      style={{ padding: "1.5rem" }}
      data-testid="project-unavailable"
    >
      <section
        className="flex flex-col"
        style={{
          width: "min(32.5rem, 100%)",
          gap: "1rem",
          padding: "1.5rem",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-3)",
          background: "var(--bg-1)",
          boxShadow: "var(--shadow-1)",
        }}
      >
        <div className="flex items-start" style={{ gap: "0.875rem" }}>
          <div
            className="flex items-center justify-center shrink-0"
            style={{
              width: "2.5rem",
              height: "2.5rem",
              borderRadius: "var(--r-2)",
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              color: "var(--fg-2)",
            }}
          >
            <LockKeyhole size="1.25rem" aria-hidden="true" />
          </div>
          <div
            className="flex flex-col"
            style={{ gap: "0.375rem", minWidth: 0 }}
          >
            <h1 style={{ margin: 0, fontSize: "1.25rem", lineHeight: 1.25 }}>
              {t("unavailable.title")}
            </h1>
            <p
              className="dim"
              style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}
            >
              {t("unavailable.message")}
            </p>
          </div>
        </div>
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", flexWrap: "wrap" }}
        >
          <button type="button" className="btn primary" onClick={onHome}>
            <Home size="0.75rem" />
            {t("unavailable.home")}
          </button>
          <button type="button" className="btn" onClick={onBack}>
            <ArrowLeft size="0.75rem" />
            {t("unavailable.back")}
          </button>
          {requestAccess && !requestAccess.sent && (
            <button
              type="button"
              className="btn"
              data-testid="request-access-open"
              onClick={() => {
                setOpen(true);
              }}
            >
              <Send size="0.75rem" />
              {t("unavailable.requestAccess")}
            </button>
          )}
        </div>
        {requestAccess?.sent && (
          <div data-testid="request-access-sent" aria-live="polite">
            <Notice
              tone="info"
              role="status"
              text={t("unavailable.requestSent")}
            />
          </div>
        )}
        {!requestAccess && (
          <p className="dim" style={{ margin: 0, fontSize: "0.75rem" }}>
            {t("unavailable.signInToRequest")}
          </p>
        )}
      </section>
      {requestAccess && (
        <Modal
          isOpen={open && !requestAccess.sent}
          onClose={() => {
            setOpen(false);
          }}
          title={t("unavailable.requestTitle")}
          footer={
            <Button
              type="button"
              disabled={requestAccess.pending}
              data-testid="request-access-submit"
              onClick={() => {
                requestAccess.onSend(
                  message.trim() === "" ? null : message.trim(),
                );
              }}
            >
              {t("unavailable.requestSend")}
            </Button>
          }
        >
          <label
            className="flex flex-col"
            style={{ gap: "0.25rem", fontSize: "0.75rem" }}
          >
            {t("unavailable.requestMessage")}
            <Textarea
              rows={3}
              maxLength={1000}
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
              }}
              data-testid="request-access-message"
            />
          </label>
          {requestAccess.failed && (
            <Notice
              tone="err"
              role="alert"
              text={t("unavailable.requestFailed")}
            />
          )}
        </Modal>
      )}
    </main>
  );
};
