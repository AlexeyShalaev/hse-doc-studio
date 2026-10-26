import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { GitContents } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import type { ParseRemoteUrlResult } from "../lib/parseRemoteUrl";
import { ConfirmCheck } from "./ConfirmCheck";
import { ContentsPreview } from "./ContentsPreview";
import { ProviderChip } from "./ProviderChip";
import { SharedFolderWarning } from "./SharedFolderWarning";
import { StepLayout } from "./StepLayout";

export type RepositoryStepProps = {
  url: string;
  onUrlChange: (value: string) => void;
  /** Поле потеряло фокус или шаг уходит дальше: пора очистить адрес от токена. */
  onUrlCommit: () => void;
  /** Токен из адреса уже убран из поля. */
  tokenStripped: boolean;
  branch: string;
  onBranchChange: (value: string) => void;
  parsed: ParseRemoteUrlResult;
  ndaRequired: boolean;
  ndaAck: boolean;
  onNdaAckChange: (value: boolean) => void;
  contents: {
    data: GitContents | undefined;
    isLoading: boolean;
    isError: boolean;
    refetch: () => void;
  };
  sharedFolder: { provider: string } | null;
  onAcknowledgeShared: () => void;
  isAcknowledging: boolean;
  onCancel: () => void;
  onNext: () => void;
};

// Шаг 1. Адрес репозитория, ветка и то, что в него попадёт.
export const RepositoryStep = ({
  url,
  onUrlChange,
  onUrlCommit,
  tokenStripped,
  branch,
  onBranchChange,
  parsed,
  ndaRequired,
  ndaAck,
  onNdaAckChange,
  contents,
  sharedFolder,
  onAcknowledgeShared,
  isAcknowledging,
  onCancel,
  onNext,
}: RepositoryStepProps) => {
  const { t } = useTranslation("gitRemote");
  const uid = useId();
  const urlId = `${uid}-url`;
  const urlHintId = `${uid}-url-hint`;
  const branchId = `${uid}-branch`;
  const [touched, setTouched] = useState(false);

  const hasText = url.trim() !== "";
  const overLimit = (contents.data?.over_limit.length ?? 0) > 0;
  // «Не тот тип адреса» ясно сразу; «не похоже на адрес» не ругаем, пока человек печатает.
  const showError =
    !parsed.ok &&
    hasText &&
    (touched || parsed.error === "url_scheme_forbidden");
  const canNext =
    parsed.ok && !overLimit && (!ndaRequired || ndaAck) && hasText;

  const submit = (): void => {
    setTouched(true);
    onUrlCommit();
    if (canNext) onNext();
  };

  return (
    <StepLayout
      id="connect-repo"
      aria-label={t("connect.steps.repo")}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      start={
        <button type="button" className="btn" onClick={onCancel}>
          {t("connect.cancel")}
        </button>
      }
      end={
        <button type="submit" className="btn primary" disabled={!canNext}>
          {t("connect.next")}
        </button>
      }
    >
      {sharedFolder && (
        <SharedFolderWarning
          provider={sharedFolder.provider}
          onAcknowledge={onAcknowledgeShared}
          isBusy={isAcknowledging}
        />
      )}

      <div className="field">
        <label htmlFor={urlId}>{t("repo.url.label")}</label>
        <input
          id={urlId}
          type="text"
          className="input mono"
          value={url}
          autoFocus
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          placeholder={t("repo.url.placeholder")}
          aria-invalid={showError}
          aria-describedby={urlHintId}
          onChange={(event) => {
            onUrlChange(event.target.value);
          }}
          onBlur={() => {
            if (hasText) setTouched(true);
            onUrlCommit();
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

      <div className="field">
        <label htmlFor={branchId}>
          {t("repo.branch.label")}{" "}
          <span style={{ color: "var(--fg-3)", fontWeight: 400 }}>
            {t("repo.branch.optional")}
          </span>
        </label>
        <input
          id={branchId}
          type="text"
          className="input mono"
          value={branch}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          placeholder={t("repo.branch.placeholder")}
          style={{ maxWidth: 240 }}
          onChange={(event) => {
            onBranchChange(event.target.value);
          }}
        />
        <p className="hint" style={{ margin: 0 }}>
          {t("repo.branch.hint")}
        </p>
      </div>

      {ndaRequired && (
        <div className="flex flex-col" style={{ gap: 8 }}>
          <Notice
            tone="warn"
            role="status"
            text={
              <>
                <strong style={{ display: "block", fontWeight: 600 }}>
                  {t("repo.nda.title")}
                </strong>
                {t("repo.nda.text")}
              </>
            }
          />
          <ConfirmCheck
            checked={ndaAck}
            onChange={onNdaAckChange}
            testId="nda-confirm"
          >
            {t("repo.nda.confirm")}
          </ConfirmCheck>
        </div>
      )}

      <ContentsPreview
        contents={contents.data}
        isLoading={contents.isLoading}
        isError={contents.isError}
        onRetry={contents.refetch}
      />
    </StepLayout>
  );
};
