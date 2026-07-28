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
        padding: "40px 20px",
      }}
    >
      <div style={{ width: "100%", maxWidth: 440, textAlign: "center" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 52,
            height: 52,
            borderRadius: 14,
            background: "var(--c-ok-soft)",
            border: "1px solid var(--c-ok)",
            marginBottom: 16,
          }}
        >
          <FolderCheck size={25} style={{ color: "var(--c-ok)" }} />
        </div>
        <h2 style={{ margin: "0 0 6px", fontSize: 19 }}>
          {t("restarting.title")}
        </h2>
        <code
          className="dim"
          style={{ fontSize: 12, wordBreak: "break-all", userSelect: "all" }}
        >
          {target}
        </code>

        <ul
          style={{
            listStyle: "none",
            margin: "24px 0 0",
            padding: 0,
            textAlign: "left",
            display: "grid",
            gap: 10,
          }}
        >
          {steps.map((step) => (
            <li
              key={step.key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 13,
                opacity: step.done ? 0.6 : 1,
              }}
            >
              {step.done ? (
                <Check
                  size={14}
                  style={{ color: "var(--c-ok)", flexShrink: 0 }}
                />
              ) : (
                <Spinner size="sm" />
              )}
              {t(`restarting.steps.${step.key}`)}
            </li>
          ))}
        </ul>

        <p className="dim" style={{ fontSize: 12, marginTop: 22 }}>
          {t("restarting.hint")}
        </p>
      </div>
    </div>
  );
};
