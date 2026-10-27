import { ExternalLink, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  PROVIDER_CATALOG,
  credentialExpiry,
  providerSpec,
  type GitProvider,
  type GitTokenInfo,
} from "@entities/git-remote";
import { Spinner } from "@shared/ui/Spinner";
import { ResultFrame, type FrameTone } from "@shared/ui/ResultFrame";
import { formatDate, shortVersion } from "../lib/formatDate";
import { extraScopes, type TokenVerdict } from "../model/tokenVerdict";
import { Btn } from "./ResultFrame";

export type TokenCheckCardProps = {
  /** null: проверка идёт. */
  verdict: TokenVerdict | null;
  provider: GitProvider;
  version?: string | null;
  /** Ссылка на выпуск нового токена с нужными правами. */
  createUrl?: string | null;
  onRetry?: () => void;
  onReviewCertificate?: () => void;
  /** Проверка идёт для токена, которого человек ещё не сохранил: «Проверить ещё раз» не нужна. */
  canRetry?: boolean;
};

const TONE: Record<TokenVerdict["kind"], FrameTone> = {
  sufficient: "ok",
  too_narrow: "err",
  too_broad: "warn",
  unknown: "info",
  expired: "err",
  error: "err",
};

const Scopes = ({ scopes }: { scopes: readonly string[] }) => (
  <span className="flex" style={{ gap: 4, flexWrap: "wrap" }}>
    {scopes.map((scope) => (
      <span key={scope} className="chip subtle mono">
        {scope}
      </span>
    ))}
  </span>
);

const Facts = ({
  info,
  providerLabel,
  version,
}: {
  info: GitTokenInfo | null;
  providerLabel: string;
  version: string | null | undefined;
}) => {
  const { t } = useTranslation("gitAccess");
  const expiry = credentialExpiry(info?.expires_at);
  const rows: [string, React.ReactNode][] = [];
  if (info?.login) {
    rows.push([
      t("tokenCheck.owner"),
      <span key="login" className="mono">
        {info.login}
      </span>,
    ]);
  }
  if (info && info.scopes.length > 0) {
    rows.push([
      t("tokenCheck.scopes"),
      <Scopes key="s" scopes={info.scopes} />,
    ]);
  }
  if (expiry.state !== "none") {
    rows.push([
      t("tokenCheck.expires"),
      expiry.state === "expired"
        ? t("tokenCheck.expiredOn", { date: formatDate(expiry.at) })
        : t("tokenCheck.expiresOn", {
            date: formatDate(expiry.at),
            count: expiry.days,
          }),
    ]);
  } else if (info) {
    rows.push([t("tokenCheck.expires"), t("tokenCheck.noExpiry")]);
  }
  if (version) {
    rows.push([
      t("tokenCheck.server"),
      `${providerLabel} ${shortVersion(version)}`,
    ]);
  }
  if (rows.length === 0) return null;
  return (
    <dl
      data-testid="token-facts"
      style={{
        margin: 0,
        display: "grid",
        gridTemplateColumns: "max-content 1fr",
        columnGap: 14,
        rowGap: 4,
        fontSize: 12,
        alignItems: "center",
      }}
    >
      {rows.map(([label, value]) => (
        <div key={label} style={{ display: "contents" }}>
          <dt className="dim">{label}</dt>
          <dd style={{ margin: 0, color: "var(--fg-0)", minWidth: 0 }}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
};

// Итог проверки токена: чей он, какие у него права и до какого срока, хватит ли
// их для чтения и отправки версий. Состояния: идёт проверка, подходит, мало прав,
// слишком широкий, проверить нельзя, срок истёк, отказ сервера.
export const TokenCheckCard = ({
  verdict,
  provider,
  version,
  createUrl = null,
  onRetry,
  onReviewCertificate,
  canRetry = true,
}: TokenCheckCardProps) => {
  const { t, i18n } = useTranslation("gitAccess");
  const spec = providerSpec(provider);
  const providerLabel = spec.label;

  if (verdict === null) {
    return (
      <div
        role="status"
        className="flex items-start"
        data-testid="token-check-running"
        style={{
          gap: 10,
          padding: "12px 14px",
          borderRadius: "var(--r-3)",
          border: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <Spinner size="sm" />
        <div>
          <div style={{ fontWeight: 600, fontSize: 13 }}>
            {t("tokenCheck.running.title")}
          </div>
          <div className="dim" style={{ fontSize: 12.5, marginTop: 2 }}>
            {t("tokenCheck.running.text")}
          </div>
        </div>
      </div>
    );
  }

  const info = verdict.info;
  const missing = (info?.missing ?? []).join(", ");
  const extra = extraScopes(info, spec.permissions.too_broad).join(", ");
  const lang = i18n.language.startsWith("en") ? "en" : "ru";
  const needs = PROVIDER_CATALOG.providers.find((p) => p.id === provider)
    ?.permissions.human[lang];

  let title: string;
  let text: string;
  if (verdict.kind === "error") {
    const known = i18n.exists(`gitAccess:tokenCheck.error.${verdict.code}`);
    title = known
      ? t(`tokenCheck.error.${verdict.code}.title`)
      : t("tokenCheck.error.generic.title");
    text = known
      ? t(`tokenCheck.error.${verdict.code}.text`)
      : t(`errors:code.${verdict.code}`, { defaultValue: verdict.detail });
  } else {
    title = t(`tokenCheck.${verdict.kind}.title`);
    text = t(`tokenCheck.${verdict.kind}.text`, {
      missing,
      extra,
      provider: providerLabel,
    });
  }

  const tls =
    verdict.kind === "error" &&
    (verdict.code === "tls_untrusted_ca" ||
      verdict.code === "tls_pin_mismatch");
  const needsNewToken =
    verdict.kind === "too_narrow" ||
    verdict.kind === "expired" ||
    (verdict.kind === "error" && verdict.code === "auth_failed");

  return (
    <ResultFrame
      tone={tls ? "warn" : TONE[verdict.kind]}
      title={title}
      testId={`token-check-${verdict.kind === "error" ? verdict.code : verdict.kind}`}
      role={verdict.kind === "sufficient" ? "status" : "alert"}
      actions={
        <>
          {tls && onReviewCertificate && (
            <Btn primary onClick={onReviewCertificate}>
              <ShieldCheck size={13} aria-hidden="true" />
              {t("tokenCheck.reviewCertificate")}
            </Btn>
          )}
          {needsNewToken && createUrl && (
            <a
              href={createUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn primary"
              style={{ gap: 6, textDecoration: "none" }}
            >
              <ExternalLink size={12} aria-hidden="true" />
              {t("tokenCheck.createNew")}
            </a>
          )}
          {canRetry && onRetry && verdict.kind !== "sufficient" && (
            <Btn onClick={onRetry}>{t("tokenCheck.retry")}</Btn>
          )}
        </>
      }
    >
      <p style={{ margin: 0 }}>{text}</p>
      {(verdict.kind === "too_narrow" || verdict.kind === "expired") &&
        needs && (
          <p className="dim" style={{ margin: 0 }}>
            {t("tokenCheck.needs", { needs })}
          </p>
        )}
      <Facts info={info} providerLabel={providerLabel} version={version} />
    </ResultFrame>
  );
};
