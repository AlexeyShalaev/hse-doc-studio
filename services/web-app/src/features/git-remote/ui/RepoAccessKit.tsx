import { useMemo, useState } from "react";
import { ScanSearch } from "lucide-react";
import {
  providerOfHost,
  useCheckCredential,
  useHostSettings,
  type GitCredential,
  type PermissionProfile,
} from "@entities/git-remote";
import { Button } from "@shared/ui/Button";
import { urlForHost } from "../lib/hostUrl";
import { parseRemoteUrl } from "../lib/parseRemoteUrl";
import { tokenCreateUrl } from "../lib/providerHelp";
import { useHostProvider } from "../model/useHostProvider";
import {
  verdictOfCheck,
  verdictOfError,
  type TokenVerdict,
} from "../model/tokenVerdict";
import { TokenCheckCard } from "./TokenCheckCard";
import { TokenLinkCard } from "./TokenLinkCard";

// Доступ к репозиторию для других разделов (Студия шаблонов): памятка о токене
// под профиль прав каталога и проверка сохранённого доступа под тот же профиль.
// Сам токен сюда не приходит: только метка доступа и итог проверки.

export type RepoTokenHelpProps = {
  /** Адрес репозитория, как его ввёл человек. */
  url: string;
  profile?: PermissionProfile | null;
  defaultOpen?: boolean;
  /** Куда вставить токен, если поля токена рядом нет (см. TokenLinkCard). */
  pasteHint?: string | null;
};

/** Памятка «как получить токен» для адреса репозитория; адрес без сайта: ничего. */
export const RepoTokenHelp = ({
  url,
  profile = null,
  defaultOpen = false,
  pasteHint = null,
}: RepoTokenHelpProps) => {
  const parsed = useMemo(() => {
    const result = parseRemoteUrl(url, { allow_http: true });
    return result.ok && result.url.kind !== "file" ? result.url : null;
  }, [url]);
  const host = useHostProvider(parsed);
  if (!host.url) return null;
  return (
    <TokenLinkCard
      url={host.url}
      profile={profile}
      defaultOpen={defaultOpen}
      pasteHint={pasteHint}
    />
  );
};

export type CredentialCheckCardProps = {
  credential: GitCredential;
  profile?: PermissionProfile | null;
  /** Подпись кнопки проверки (на языке раздела, который её показывает). */
  checkLabel: string;
};

type CheckState =
  null | "running" | { verdict: TokenVerdict; version: string | null };

/** Проверка сохранённого доступа под профиль прав: кнопка, затем итог проверки. */
export const CredentialCheckCard = ({
  credential,
  profile = null,
  checkLabel,
}: CredentialCheckCardProps) => {
  const check = useCheckCredential(profile);
  const hostSettings = useHostSettings();
  const provider = providerOfHost(credential.host, null, hostSettings.data).id;
  const [state, setState] = useState<CheckState>(null);
  const createUrl = tokenCreateUrl(urlForHost(credential.host, provider), {
    provider,
    profile,
  });

  const run = async (): Promise<void> => {
    setState("running");
    try {
      const result = await check.mutateAsync(credential.id);
      setState({
        verdict: verdictOfCheck(result),
        version: result.provider_info.version ?? null,
      });
    } catch (caught) {
      setState({
        verdict: verdictOfError(caught, credential.expires_at),
        version: null,
      });
    }
  };

  if (state === null) {
    return (
      <div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void run()}
          data-testid="credential-check"
        >
          <ScanSearch size="0.75rem" aria-hidden="true" />
          {checkLabel}
        </Button>
      </div>
    );
  }
  return (
    <TokenCheckCard
      verdict={state === "running" ? null : state.verdict}
      version={state === "running" ? null : state.version}
      provider={provider}
      profile={profile}
      createUrl={createUrl}
      onRetry={() => void run()}
    />
  );
};
