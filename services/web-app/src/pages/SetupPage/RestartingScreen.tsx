import { useTranslation } from "react-i18next";
import { Check, FolderCheck } from "lucide-react";
import { Spinner } from "@shared/ui/Spinner";

type RestartingScreenProps = {
  target: string;
};

/**
 * Ожидание, пока приложение пересоздаёт само себя.
 *
 * Держать пользователя перед одним спиннером минуту нельзя: он решит, что всё
 * зависло, и полезет перезагружать страницу — а страница в этот момент как раз
 * и ждёт возвращения сервера. Поэтому показываем, что именно происходит, и
 * называем выбранную папку: это единственное подтверждение, что применилось
 * ровно то, что он выбрал.
 */
export const RestartingScreen = ({ target }: RestartingScreenProps) => {
  const { t } = useTranslation("setup");
  const steps = [
    { key: "saved", done: true },
    { key: "recreating", done: false },
    { key: "waiting", done: false },
  ];

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2.5rem 1.25rem",
      }}
    >
      <div style={{ width: "100%", maxWidth: "27.5rem", textAlign: "center" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: "3.25rem",
            height: "3.25rem",
            borderRadius: "0.875rem",
            background: "var(--c-ok-soft)",
            border: "1px solid var(--c-ok)",
            marginBottom: "1rem",
          }}
        >
          <FolderCheck size="1.5625rem" style={{ color: "var(--c-ok)" }} />
        </div>
        <h2 style={{ margin: "0 0 0.375rem", fontSize: "1.1875rem" }}>
          {t("restarting.title")}
        </h2>
        <code
          className="dim"
          style={{
            fontSize: "0.75rem",
            wordBreak: "break-all",
            userSelect: "all",
          }}
        >
          {target}
        </code>

        <ul
          style={{
            listStyle: "none",
            margin: "1.5rem 0 0",
            padding: 0,
            textAlign: "left",
            display: "grid",
            gap: "0.625rem",
          }}
        >
          {steps.map((step) => (
            <li
              key={step.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.625rem",
                fontSize: "0.8125rem",
                opacity: step.done ? 0.6 : 1,
              }}
            >
              {step.done ? (
                <Check
                  size="0.875rem"
                  style={{ color: "var(--c-ok)", flexShrink: 0 }}
                />
              ) : (
                <Spinner size="sm" />
              )}
              {t(`restarting.steps.${step.key}`)}
            </li>
          ))}
        </ul>

        <p
          className="dim"
          style={{ fontSize: "0.75rem", marginTop: "1.375rem" }}
        >
          {t("restarting.hint")}
        </p>
      </div>
    </div>
  );
};
