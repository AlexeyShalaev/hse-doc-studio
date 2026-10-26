import { useTranslation } from "react-i18next";
import type { GitCredential } from "@entities/git-remote";
import { Spinner } from "@shared/ui/Spinner";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { useRemoteAuth } from "../model/useRemoteAuth";
import { ProviderChip } from "./ProviderChip";
import { RemoteAuthFields } from "./RemoteAuthFields";
import { StepLayout } from "./StepLayout";

export type { AccessMethod } from "../model/useRemoteAuth";

export type AccessStepProps = {
  url: ParsedRemoteUrl;
  /** `fix_access`: адрес не меняется, доступ обновляется у уже подключённого проекта. */
  fixing: boolean;
  /** Доступ, с которым проект подключён сейчас (для `fix_access`). */
  bound: { id: string; label: string; kind: string } | null;
  credentials: GitCredential[];
  isLoadingCredentials: boolean;
  /** false: хранилище секретов недоступно, сохранить токен или ключ нельзя. */
  secretsOk: boolean;
  /** Доступ выбран (или сохранён): можно проверять подключение. */
  onContinue: (credentialId: string) => void;
  onBack: () => void;
  onSwitchUrl: (value: string) => void;
};

// Шаг 2. Как репозиторий узнает, что это ты: токен по https или ключ по ssh.
export const AccessStep = ({
  url,
  fixing,
  bound,
  credentials,
  isLoadingCredentials,
  secretsOk,
  onContinue,
  onBack,
  onSwitchUrl,
}: AccessStepProps) => {
  const { t: tRemote } = useTranslation("gitRemote");
  const auth = useRemoteAuth({
    url,
    fixing,
    bound,
    credentials,
    secretsOk,
    onResolved: (id) => {
      // Без «Без доступа» id здесь всегда есть.
      if (id !== null) onContinue(id);
    },
  });

  return (
    <StepLayout
      id="connect-access"
      aria-label={tRemote("connect.steps.access")}
      onSubmit={(event) => {
        event.preventDefault();
        if (auth.canSubmit) auth.submit();
      }}
      start={
        <button type="button" className="btn" onClick={onBack}>
          {fixing ? tRemote("connect.cancel") : tRemote("connect.back")}
        </button>
      }
      end={
        <button
          type="submit"
          className="btn primary"
          disabled={!auth.canSubmit}
        >
          {auth.isSaving && <Spinner size="sm" />}
          {auth.submitLabel}
        </button>
      }
    >
      {fixing && (
        <div
          style={{
            padding: "8px 10px",
            borderRadius: "var(--r-2)",
            background: "var(--bg-2)",
            border: "1px solid var(--border)",
          }}
        >
          <ProviderChip url={url} />
        </div>
      )}

      <RemoteAuthFields
        auth={auth}
        url={url}
        fixing={fixing}
        bound={bound}
        isLoadingCredentials={isLoadingCredentials}
        secretsOk={secretsOk}
        onSwitchUrl={onSwitchUrl}
      />
    </StepLayout>
  );
};
