import type { AdminOidcProvider, RegistrationMode } from "@entities/session";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Домены из строки через запятую, пробел или перенос: нижний регистр, без @, без повторов. */
export const parseDomains = (text: string): string[] => {
  const seen = new Set<string>();
  for (const raw of text.split(/[\s,;]+/)) {
    const domain = raw.trim().replace(/^@/, "").toLowerCase();
    if (domain !== "") seen.add(domain);
  }
  return [...seen];
};

const DOMAIN = /^(?=.{1,253}$)([a-z0-9-]+\.)+[a-z]{2,}$/;
export const invalidDomains = (domains: readonly string[]): string[] =>
  domains.filter((d) => !DOMAIN.test(d));

export const isEmail = (value: string): boolean => EMAIL.test(value.trim());

export const approvalApplies = (mode: RegistrationMode): boolean =>
  mode === "open" || mode === "domains";

// ---- OIDC ----

export type OidcDraft = {
  label: string;
  issuer: string;
  client_id: string;
  client_secret: string;
  scopes: string;
  enabled: boolean;
  auto_provision: boolean;
};

export const DEFAULT_SCOPES = "openid email profile";

export const emptyOidcDraft = (): OidcDraft => ({
  label: "",
  issuer: "",
  client_id: "",
  client_secret: "",
  scopes: DEFAULT_SCOPES,
  enabled: true,
  auto_provision: false,
});

export const draftOfProvider = (provider: AdminOidcProvider): OidcDraft => ({
  label: provider.label,
  issuer: provider.issuer,
  client_id: provider.client_id,
  // Секрет сервер не отдаёт: поле пустое, пока человек не введёт новый.
  client_secret: "",
  scopes: provider.scopes,
  enabled: provider.enabled,
  auto_provision: provider.auto_provision,
});

export type OidcIssueKey =
  | "labelRequired"
  | "issuerRequired"
  | "issuerInvalid"
  | "issuerInsecure"
  | "clientIdRequired"
  | "secretRequired"
  | "scopesOpenid";

export type OidcIssues = Partial<
  Record<
    "label" | "issuer" | "client_id" | "client_secret" | "scopes",
    OidcIssueKey
  >
>;

const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\])$/;

/** Проверка формы провайдера до отправки: адрес издателя, обязательные поля, scope openid. */
export const validateOidc = (
  draft: OidcDraft,
  options: { creating: boolean },
): OidcIssues => {
  const issues: OidcIssues = {};
  if (draft.label.trim() === "") issues.label = "labelRequired";
  const issuer = draft.issuer.trim();
  if (issuer === "") {
    issues.issuer = "issuerRequired";
  } else {
    try {
      const url = new URL(issuer);
      if (url.protocol !== "https:" && url.protocol !== "http:") {
        issues.issuer = "issuerInvalid";
      } else if (url.protocol === "http:" && !LOCAL_HOST.test(url.hostname)) {
        issues.issuer = "issuerInsecure";
      } else if (url.search !== "" || url.hash !== "") {
        issues.issuer = "issuerInvalid";
      }
    } catch {
      issues.issuer = "issuerInvalid";
    }
  }
  if (draft.client_id.trim() === "") issues.client_id = "clientIdRequired";
  if (options.creating && draft.client_secret === "") {
    issues.client_secret = "secretRequired";
  }
  if (!draft.scopes.split(/\s+/).includes("openid")) {
    issues.scopes = "scopesOpenid";
  }
  return issues;
};

/** Адрес, который нужно внести у провайдера как redirect URI. */
export const redirectUri = (baseUrl: string, providerId: string): string =>
  `${baseUrl.replace(/\/+$/, "")}/auth/oidc/${providerId}/callback`;

// ---- SMTP ----

export type SmtpDraft = {
  host: string;
  port: string;
  security: "starttls" | "tls" | "none";
  username: string;
  password: string;
  from_address: string;
  from_name: string;
};

export type SmtpIssueKey = "hostRequired" | "portInvalid" | "fromInvalid";
export type SmtpIssues = Partial<
  Record<"host" | "port" | "from_address", SmtpIssueKey>
>;

export const validateSmtp = (draft: SmtpDraft): SmtpIssues => {
  const issues: SmtpIssues = {};
  if (draft.host.trim() === "") issues.host = "hostRequired";
  const port = Number(draft.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    issues.port = "portInvalid";
  }
  if (!isEmail(draft.from_address)) issues.from_address = "fromInvalid";
  return issues;
};

export const DEFAULT_PORT: Record<SmtpDraft["security"], number> = {
  starttls: 587,
  tls: 465,
  none: 25,
};
