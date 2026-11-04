import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { KEY_STEPS, USER_KEY_STEPS, sshLinksFor } from "../lib/providerHelp";
import { useInstancePathStore } from "../model/useInstancePathStore";

export type KeyScope = "deploy" | "user";

export type ProviderHelpProps = {
  /** Адрес с уже решённым провайдером (см. useHostProvider). */
  url: ParsedRemoteUrl;
  /** Куда добавляем ключ: в репозиторий (deploy-ключ) или в профиль (ключ пользователя). */
  scope: KeyScope;
  /** Раскрыть сразу (например, когда ключ только что создан). */
  defaultOpen?: boolean;
};

// Пошаговая памятка по ключу с прямой ссылкой на нужную страницу сервера. Шаги у
// каждого провайдера свои, поэтому тексты лежат в переводах по провайдеру. Страницы
// ключей открываются без подстановки: публичный ключ берут из поля выше.
export const ProviderHelp = ({
  url,
  scope,
  defaultOpen = false,
}: ProviderHelpProps) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const subpath = useInstancePathStore((state) =>
    url.host ? (state.paths[url.host.toLowerCase()] ?? "") : "",
  );
  const provider = url.provider;
  const steps =
    scope === "deploy" ? KEY_STEPS[provider] : USER_KEY_STEPS[provider];
  const prefix = scope === "deploy" ? "key" : "userKey";
  const links = sshLinksFor(url, { provider, subpath });
  const link = scope === "deploy" ? links?.deployKey : links?.userKeys;
  const providerName = tRemote(`provider.${provider}`);

  return (
    <details
      className="sync-details"
      open={defaultOpen}
      data-testid={`provider-help-${scope}`}
    >
      <summary>{t("help.keySummary", { provider: providerName })}</summary>
      <div style={{ marginTop: "0.5rem" }}>
        <ol
          style={{
            margin: 0,
            paddingLeft: "1.25rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.3125rem",
            fontSize: "0.75rem",
            lineHeight: 1.5,
            color: "var(--fg-1)",
          }}
        >
          {steps.map((step) => (
            <li key={step}>{t(`help.${provider}.${prefix}.${step}`)}</li>
          ))}
        </ol>
        {link && (
          <a
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn sm"
            data-testid={`key-page-link-${scope}`}
            style={{
              marginTop: "0.625rem",
              gap: "0.375rem",
              textDecoration: "none",
            }}
          >
            <ExternalLink size="0.75rem" aria-hidden="true" />
            {scope === "deploy"
              ? t("help.openDeployKeyPage", { provider: providerName })
              : t("help.openKeyPage", { provider: providerName })}
          </a>
        )}
        <p
          className="dim"
          style={{ margin: "0.5rem 0 0", fontSize: "0.71875rem" }}
        >
          {t("help.keyNote")}
        </p>
      </div>
    </details>
  );
};
