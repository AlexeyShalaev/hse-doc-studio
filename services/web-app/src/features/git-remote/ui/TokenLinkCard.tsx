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

const linkStyle: React.CSSProperties = { gap: 6, textDecoration: "none" };

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
        gap: 12,
        padding: 14,
        borderRadius: "var(--r-3)",
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex items-center" style={{ gap: 8 }}>
        <span
          aria-hidden="true"
          className="flex items-center justify-center"
          style={{
            width: 24,
            height: 24,
            borderRadius: "50%",
            background: "var(--accent-soft)",
            color: "var(--accent)",
            flexShrink: 0,
          }}
        >
          <KeyRound size={13} />
        </span>
        <strong style={{ fontSize: 13 }}>{t("tokenLink.title")}</strong>
      </div>

      {legacy && (
        <p
          className="flex items-start"
          data-testid="gitlab-legacy-note"
          style={{
            margin: 0,
            gap: 7,
            fontSize: 12,
            lineHeight: 1.45,
            color: "var(--fg-1)",
          }}
        >
          <TriangleAlert
            size={13}
            aria-hidden="true"
            style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 2 }}
          />
          {t("tokenLink.legacyGitlab", { version: serverVersion })}
        </p>
      )}

      {primary && (
        <div
          className="flex flex-col"
          style={{ gap: 6, alignItems: "flex-start" }}
        >
          <a
            href={primary.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn primary"
            data-testid="token-create-link"
            style={linkStyle}
          >
            <ExternalLink size={13} aria-hidden="true" />
            {prefilled
              ? t("tokenLink.create", { provider: providerName })
              : t("tokenLink.open", { provider: providerName })}
          </a>
          <span className="dim" style={{ fontSize: 11.5 }}>
            {prefilled ? t("tokenLink.prefilled") : t("tokenLink.plain")}
          </span>
        </div>
      )}

      <div className="flex flex-col" style={{ gap: 5 }}>
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("tokenLink.rights")}
        </span>
        {spec.permissions.required.length > 0 && provider !== "other" && (
          <span className="flex" style={{ gap: 4, flexWrap: "wrap" }}>
            {spec.permissions.required.map((scope) => (
              <span key={scope} className="chip accent mono">
                {scope}
              </span>
            ))}
          </span>
        )}
        <span style={{ fontSize: 12 }}>{spec.permissions.human[lang]}</span>
      </div>

      <ol
        aria-label={t("tokenLink.helper.label")}
        data-testid="token-helper-steps"
        style={{
          margin: 0,
          padding: 0,
          listStyle: "none",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 8,
        }}
      >
        {HELPER.map((id, index) => (
          <li
            key={id}
            className="flex items-start"
            style={{
              gap: 8,
              padding: "8px 10px",
              borderRadius: "var(--r-2)",
              background: "var(--bg-2)",
              fontSize: 12,
              lineHeight: 1.4,
            }}
          >
            <span
              aria-hidden="true"
              className="flex items-center justify-center"
              style={{
                width: 18,
                height: 18,
                borderRadius: "50%",
                border: "1px solid var(--accent-line)",
                color: "var(--accent)",
                fontSize: 11,
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
            gap: 7,
            fontSize: 12,
            lineHeight: 1.45,
            color: "var(--fg-1)",
          }}
        >
          <TriangleAlert
            size={13}
            aria-hidden="true"
            style={{ color: "var(--c-warn)", flexShrink: 0, marginTop: 2 }}
          />
          {t("tokenLink.githubRepo")}
        </p>
      )}
      {provider === "gitlab" && (
        <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
          {t("tokenLink.gitlabNote")}
        </p>
      )}

      {fallback && (
        <div
          className="flex flex-col"
          data-testid="token-fallback"
          style={{ gap: 4, fontSize: 12 }}
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
              style={{ fontSize: 11.5, color: "var(--c-warn)" }}
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
            margin: "8px 0 0",
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
            <li key={step}>{t(`help.${provider}.token.${step}`)}</li>
          ))}
        </ol>
      </details>

      <div
        className="flex items-center dim"
        style={{ gap: 12, flexWrap: "wrap", fontSize: 11.5 }}
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
