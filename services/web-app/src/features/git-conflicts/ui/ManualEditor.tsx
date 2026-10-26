import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CodeEditor } from "@shared/ui/CodeEditor";
import { Notice } from "@shared/ui/ConflictKit";
import { editorLanguageFor } from "../lib/editorLanguage";
import { hasConflictMarkers } from "../model/conflictModel";

export type ManualEditorProps = {
  path: string;
  /** С чего начать: файл как он получится при текущих выборах. */
  initialText: string;
  /** Текст, уже принятый как решение (правка вручную сохранена), либо null. */
  appliedText: string | null;
  disabled: boolean;
  onApply: (content: string) => void;
};

/**
 * Ручная правка итогового файла. Принять текст с метками конфликта нельзя:
 * они ушли бы в репозиторий коллегам и сломали бы сборку.
 */
export const ManualEditor = ({
  path,
  initialText,
  appliedText,
  disabled,
  onApply,
}: ManualEditorProps) => {
  const { t } = useTranslation("gitConflicts");
  const [text, setText] = useState(appliedText ?? initialText);
  const markers = hasConflictMarkers(text);
  const isApplied = appliedText !== null && appliedText === text;
  const base = appliedText ?? initialText;

  return (
    <div className="flex flex-col" style={{ gap: 8, minWidth: 0 }}>
      <p className="dim" style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}>
        {t("manual.hint")}
      </p>
      <div
        className="card"
        style={{
          height: 420,
          overflow: "hidden",
          borderColor: markers ? "var(--c-err)" : undefined,
        }}
      >
        <CodeEditor
          value={text}
          onChange={setText}
          language={editorLanguageFor(path)}
          wrapLines
          ariaLabel={t("manual.aria", { path })}
        />
      </div>
      {markers && <Notice tone="err" role="alert" text={t("manual.markers")} />}
      <div className="flex items-center" style={{ gap: 8 }}>
        <button
          type="button"
          className="btn primary"
          disabled={disabled || markers || isApplied}
          onClick={() => {
            onApply(text);
          }}
        >
          {isApplied ? t("manual.applied") : t("manual.apply")}
        </button>
        <button
          type="button"
          className="btn"
          disabled={text === base}
          onClick={() => {
            setText(base);
          }}
        >
          {t("manual.reset")}
        </button>
      </div>
    </div>
  );
};
