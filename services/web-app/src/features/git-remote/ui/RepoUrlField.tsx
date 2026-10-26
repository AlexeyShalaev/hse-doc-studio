import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import type { ParseRemoteUrlResult } from "../lib/parseRemoteUrl";
import { ProviderChip } from "./ProviderChip";

export type RepoUrlFieldProps = {
  url: string;
  onChange: (value: string) => void;
  /** Поле потеряло фокус или шаг уходит дальше: пора очистить адрес от токена. */
  onCommit: () => void;
  parsed: ParseRemoteUrlResult;
  /** Токен из адреса уже убран из поля. */
  tokenStripped: boolean;
  /** Показать причину, даже если поле ещё не трогали (шаг пытались закончить). */
  forceError?: boolean;
  autoFocus?: boolean;
  disabled?: boolean;
};

// Поле адреса репозитория: под ним сразу видно, что мы поняли из строки
// (сервер, владелец, репозиторий), а для неподходящего адреса причину.
export const RepoUrlField = ({
  url,
  onChange,
  onCommit,
  parsed,
  tokenStripped,
  forceError = false,
  autoFocus = true,
  disabled = false,
}: RepoUrlFieldProps) => {
  const { t } = useTranslation("gitRemote");
  const uid = useId();
  const urlId = `${uid}-url`;
  const urlHintId = `${uid}-url-hint`;
  const [touched, setTouched] = useState(false);

  const hasText = url.trim() !== "";
  // «Не тот тип адреса» ясно сразу; «не похоже на адрес» не ругаем, пока человек печатает.
  const showError =
    !parsed.ok &&
    hasText &&
    (touched || forceError || parsed.error === "url_scheme_forbidden");

  return (
    <>
      <div className="field">
        <label htmlFor={urlId}>{t("repo.url.label")}</label>
        <input
          id={urlId}
          type="text"
          className="input mono"
          value={url}
          autoFocus={autoFocus}
          disabled={disabled}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          placeholder={t("repo.url.placeholder")}
          aria-invalid={showError}
          aria-describedby={urlHintId}
          onChange={(event) => {
            onChange(event.target.value);
          }}
          onBlur={() => {
            if (hasText) setTouched(true);
            onCommit();
          }}
        />
        <div id={urlHintId} style={{ minHeight: 20 }}>
          {parsed.ok ? (
            <ProviderChip url={parsed.url} />
          ) : showError ? (
            <p
              className="text-xs"
              role="alert"
              style={{ margin: 0, color: "var(--c-err)" }}
            >
              {t(`errors:code.${parsed.error}`)}
            </p>
          ) : (
            <p className="hint" style={{ margin: 0 }}>
              {t("repo.url.hint")}
            </p>
          )}
        </div>
      </div>

      {((parsed.ok && parsed.url.token_stripped) || tokenStripped) && (
        <Notice tone="info" role="status" text={t("repo.url.tokenStripped")} />
      )}
    </>
  );
};
