import { ExternalLink, KeyRound, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { providerSpec } from "@entities/git-remote";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { TOKEN_STEPS, tokenLinksFor } from "../lib/providerHelp";
import { useInstancePathStore } from "../model/useInstancePathStore";

export type TokenLinkCardProps = {
  /** Адрес с уже решённым провайдером (см. useHostProvider). */
  url: ParsedRemoteUrl;
  /** Название проекта: попадает в имя токена. */
  projectName?: string | null;
  /** Раскрыть подробные шаги сразу (когда токена нет вовсе). */
  defaultOpen?: boolean;
  /** Версия сервера, если она известна: у старого GitLab другая страница токенов. */
  serverVersion?: string | null;
};

// Страница токенов переехала в «/-/user_settings» в GitLab 16; на более старых
// версиях открывается прежняя «/-/profile».
const LEGACY_GITLAB_MAJOR = 15;

const majorOf = (version: string | null | undefined): number | null => {
  const match = /^v?(\d+)/.exec(version?.trim() ?? "");
  return match?.[1] ? Number(match[1]) : null;
};

const linkStyle: React.CSSProperties = {
  gap: "0.375rem",
  textDecoration: "none",
};

const HELPER = ["create", "copy", "paste"] as const;

// Выпуск токена одной ссылкой: страница провайдера открывается с названием,
// описанием и минимальными правами. Там, где страница не принимает подстановку,
// остаются номерные шаги. Права токена перечислены явно: без api, без лишнего.
export const TokenLinkCard = ({
  url,
  projectName = null,
  defaultOpen = false,
  serverVersion = null,
}: TokenLinkCardProps) => {
  const { t, i18n } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const provider = url.provider;
  const spec = providerSpec(provider);
  const subpath = useInstancePathStore((state) =>
    url.host ? (state.paths[url.host.toLowerCase()] ?? "") : "",
  );
  const lang = i18n.language.startsWith("en") ? "en" : "ru";
  const links = tokenLinksFor(url, { provider, subpath, projectName, lang });
  const major = majorOf(serverVersion);
  const legacy =
    provider === "gitlab" &&
    major !== null &&
    major <= LEGACY_GITLAB_MAJOR &&
    links?.fallback != null;
  // На старом GitLab главной становится ссылка для старых версий.
  const primary = (legacy ? links.fallback : links?.primary) ?? null;
  const fallback = (legacy ? links.primary : links?.fallback) ?? null;
  const providerName = tRemote(`provider.${provider}`);
  const prefilled = primary?.kind === "prefilled";
  const steps = TOKEN_STEPS[provider];

  return (
    <section
      className="flex flex-col"
      data-testid="token-link-card"
      aria-label={t("tokenLink.title")}
      style={{
        gap: "0.75rem",
        padding: "0.875rem",
        borderRadius: "var(--r-3)",
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex items-center" style={{ gap: "0.5rem" }}>
        <span
          aria-hidden="true"
          className="flex items-center justify-center"
          style={{
            width: "1.5rem",
            height: "1.5rem",
            borderRadius: "50%",
            background: "var(--accent-soft)",
            color: "var(--accent)",
            flexShrink: 0,
          }}
        >
          <KeyRound size="0.8125rem" />
        </span>
        <strong style={{ fontSize: "0.8125rem" }}>
          {t("tokenLink.title")}
        </strong>
      </div>

      {legacy && (
        <p
          className="flex items-start"
          data-testid="gitlab-legacy-note"
          style={{
            margin: 0,
            gap: "0.4375rem",
            fontSize: "0.75rem",
            lineHeight: 1.45,
            color: "var(--fg-1)",
          }}
        >
          <TriangleAlert
            size="0.8125rem"
            aria-hidden="true"
            style={{
              color: "var(--c-warn)",
              flexShrink: 0,
              marginTop: "0.125rem",
            }}
          />
          {t("tokenLink.legacyGitlab", { version: serverVersion })}
        </p>
      )}

      {primary && (
        <div
          className="flex flex-col"
          style={{ gap: "0.375rem", alignItems: "flex-start" }}
        >
          <a
            href={primary.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn primary"
            data-testid="token-create-link"
            style={linkStyle}
          >
            <ExternalLink size="0.8125rem" aria-hidden="true" />
            {prefilled
              ? t("tokenLink.create", { provider: providerName })
              : t("tokenLink.open", { provider: providerName })}
          </a>
          <span className="dim" style={{ fontSize: "0.71875rem" }}>
            {prefilled ? t("tokenLink.prefilled") : t("tokenLink.plain")}
          </span>
        </div>
      )}

      <div className="flex flex-col" style={{ gap: "0.3125rem" }}>
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {t("tokenLink.rights")}
        </span>
        {spec.permissions.required.length > 0 && provider !== "other" && (
          <span className="flex" style={{ gap: "0.25rem", flexWrap: "wrap" }}>
            {spec.permissions.required.map((scope) => (
              <span key={scope} className="chip accent mono">
                {scope}
              </span>
            ))}
          </span>
        )}
        <span style={{ fontSize: "0.75rem" }}>
          {spec.permissions.human[lang]}
        </span>
      </div>

      <ol
        aria-label={t("tokenLink.helper.label")}
        data-testid="token-helper-steps"
        style={{
          margin: 0,
          padding: 0,
          listStyle: "none",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(9.375rem, 1fr))",
          gap: "0.5rem",
        }}
      >
        {HELPER.map((id, index) => (
          <li
            key={id}
            className="flex items-start"
            style={{
              gap: "0.5rem",
              padding: "0.5rem 0.625rem",
              borderRadius: "var(--r-2)",
              background: "var(--bg-2)",
              fontSize: "0.75rem",
              lineHeight: 1.4,
            }}
          >
            <span
              aria-hidden="true"
              className="flex items-center justify-center"
              style={{
                width: "1.125rem",
                height: "1.125rem",
                borderRadius: "50%",
                border: "1px solid var(--accent-line)",
                color: "var(--accent)",
                fontSize: "0.6875rem",
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              {index + 1}
            </span>
            <span>
              <strong style={{ display: "block", fontWeight: 600 }}>
                {t(`tokenLink.helper.${id}.title`)}
              </strong>
              <span className="dim">{t(`tokenLink.helper.${id}.text`)}</span>
            </span>
          </li>
        ))}
      </ol>

      {provider === "github" && prefilled && (
        <p
          className="flex items-start"
          data-testid="github-repo-note"
          style={{
            margin: 0,
            gap: "0.4375rem",
            fontSize: "0.75rem",
            lineHeight: 1.45,
            color: "var(--fg-1)",
          }}
        >
          <TriangleAlert
            size="0.8125rem"
            aria-hidden="true"
            style={{
              color: "var(--c-warn)",
              flexShrink: 0,
              marginTop: "0.125rem",
            }}
          />
          {t("tokenLink.githubRepo")}
        </p>
      )}
      {provider === "gitlab" && (
        <p className="dim" style={{ margin: 0, fontSize: "0.71875rem" }}>
          {t("tokenLink.gitlabNote")}
        </p>
      )}

      {fallback && (
        <div
          className="flex flex-col"
          data-testid="token-fallback"
          style={{ gap: "0.25rem", fontSize: "0.75rem" }}
        >
          <span className="dim">
            {t(
              legacy
                ? "tokenLink.fallback.gitlabNew.lead"
                : `tokenLink.fallback.${provider}.lead`,
            )}
          </span>
          <a
            href={fallback.url}
            target="_blank"
            rel="noopener noreferrer"
            className="sync-history-link"
            style={{ alignSelf: "flex-start" }}
          >
            {t(
              legacy
                ? "tokenLink.fallback.gitlabNew.link"
                : `tokenLink.fallback.${provider}.link`,
            )}
          </a>
          {fallback.broad && (
            <span
              style={{ fontSize: "0.71875rem", color: "var(--c-warn)" }}
              data-testid="token-broad-warning"
            >
              {t("tokenLink.broad")}
            </span>
          )}
        </div>
      )}

      <details className="sync-details" open={defaultOpen || !prefilled}>
        <summary>{t("tokenLink.steps")}</summary>
        <ol
          style={{
            margin: "0.5rem 0 0",
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
            <li key={step}>{t(`help.${provider}.token.${step}`)}</li>
          ))}
        </ol>
      </details>

      <div
        className="flex items-center dim"
        style={{ gap: "0.75rem", flexWrap: "wrap", fontSize: "0.71875rem" }}
      >
        <span>{t("help.tokenNote")}</span>
        {spec.docs_url && (
          <a
            href={spec.docs_url}
            target="_blank"
            rel="noopener noreferrer"
            className="sync-history-link"
          >
            {t("tokenLink.docs", { provider: providerName })}
          </a>
        )}
      </div>
    </section>
  );
};
