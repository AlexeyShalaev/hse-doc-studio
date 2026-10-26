import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import {
  KEY_STEPS,
  TOKEN_STEPS,
  deployKeyUrl,
  tokenCreateUrl,
} from "../lib/providerHelp";

export type ProviderHelpProps = {
  url: ParsedRemoteUrl;
  /** Что объясняем: как получить токен или как добавить ключ. */
  kind: "token" | "key";
  /** Раскрыть сразу (например, когда доступа ещё нет вовсе). */
  defaultOpen?: boolean;
};

// Пошаговая памятка с прямой ссылкой на нужную страницу сервера. Сами шаги у
// каждого провайдера свои, поэтому тексты лежат в переводах по провайдеру.
export const ProviderHelp = ({
  url,
  kind,
  defaultOpen = false,
}: ProviderHelpProps) => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const steps = (kind === "token" ? TOKEN_STEPS : KEY_STEPS)[url.provider];
  const link = kind === "token" ? tokenCreateUrl(url) : deployKeyUrl(url);
  const providerName = tRemote(`provider.${url.provider}`);

  return (
    <details
      className="sync-details"
      open={defaultOpen}
      data-testid={`provider-help-${kind}`}
    >
      <summary>
        {kind === "token"
          ? t("help.tokenSummary", { provider: providerName })
          : t("help.keySummary", { provider: providerName })}
      </summary>
      <div style={{ marginTop: 8 }}>
        <ol
          style={{
            margin: 0,
            paddingLeft: 20,
            display: "flex",
            flexDirection: "column",
            gap: 5,
            fontSize: 12,
            lineHeight: 1.5,
            color: "var(--fg-1)",
          }}
        >
          {steps.map((step) => (
            <li key={step}>{t(`help.${url.provider}.${kind}.${step}`)}</li>
          ))}
        </ol>
        {link && (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="btn sm"
            style={{ marginTop: 10, gap: 6, textDecoration: "none" }}
          >
            <ExternalLink size={12} aria-hidden="true" />
            {kind === "token"
              ? t("help.openTokenPage", { provider: providerName })
              : t("help.openKeyPage", { provider: providerName })}
          </a>
        )}
        <p className="dim" style={{ margin: "8px 0 0", fontSize: 11.5 }}>
          {kind === "token" ? t("help.tokenNote") : t("help.keyNote")}
        </p>
      </div>
    </details>
  );
};
