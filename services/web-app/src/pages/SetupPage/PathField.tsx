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
    <form onSubmit={handleSubmit} style={{ marginTop: 12 }}>
      <label
        htmlFor="setup-path"
        className="dim"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 11,
          marginBottom: 5,
        }}
      >
        <Keyboard size={12} />
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
          fontSize: 12.5,
        }}
      />
      {isRelative && (
        <div
          role="alert"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 7,
            marginTop: 7,
            fontSize: 12,
            color: "var(--c-warn)",
          }}
        >
          <AlertTriangle size={13} style={{ flexShrink: 0 }} />
          {t("folder.relativeWarning")}
        </div>
      )}
    </form>
  );
};
