import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Keyboard } from "lucide-react";

type PathFieldProps = {
  value: string;
  isRelative: boolean;
  onChange: (path: string) => void;
};

/**
 * Ввод пути руками — запасной путь к той же цели, что и обзор мышкой.
 *
 * Держим СВОЁ состояние и отдаём наверх только по Enter или потере фокуса:
 * каждый переход по пути стоит запуска контейнера, и слать запрос на каждую
 * набранную букву значило бы устроить очередь из десятка контейнеров на одно
 * слово.
 */
export const PathField = ({ value, isRelative, onChange }: PathFieldProps) => {
  const { t } = useTranslation("setup");
  const [draft, setDraft] = useState(value);
  const [shown, setShown] = useState(value);

  // Клик по папке в обзоре меняет путь снаружи — поле обязано это подхватить.
  // Правка прямо в рендере, а не в эффекте: так React перерисует поле в том же
  // проходе, без лишнего кадра со старым путём (рекомендованный приём «подгонки
  // состояния под изменившийся пропс»).
  if (value !== shown) {
    setShown(value);
    setDraft(value);
  }

  const commit = () => {
    const next = draft.trim();
    if (next !== "" && next !== value) onChange(next);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    commit();
  };

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: "0.75rem" }}>
      <label
        htmlFor="setup-path"
        className="dim"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.375rem",
          fontSize: "0.6875rem",
          marginBottom: "0.3125rem",
        }}
      >
        <Keyboard size="0.75rem" />
        {t("folder.typeLabel")}
      </label>
      <input
        id="setup-path"
        className="input"
        value={draft}
        spellCheck={false}
        autoComplete="off"
        onChange={(event) => {
          setDraft(event.target.value);
        }}
        onBlur={commit}
        style={{
          width: "100%",
          fontFamily: "var(--font-mono, monospace)",
          fontSize: "0.78125rem",
        }}
      />
      {isRelative && (
        <div
          role="alert"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.4375rem",
            marginTop: "0.4375rem",
            fontSize: "0.75rem",
            color: "var(--c-warn)",
          }}
        >
          <AlertTriangle size="0.8125rem" style={{ flexShrink: 0 }} />
          {t("folder.relativeWarning")}
        </div>
      )}
    </form>
  );
};
