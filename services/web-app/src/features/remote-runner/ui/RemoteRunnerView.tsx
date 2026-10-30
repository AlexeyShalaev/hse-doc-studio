import { useId, useState, type FormEvent } from "react";
import { Cloud, ExternalLink, Laptop } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import {
  Button,
  Input,
  Section,
  SettingRow,
  Spinner,
  StatusDot,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import {
  REMOTE_STATE_DOT,
  isValidEndpointName,
  isValidServerUrl,
  type RemoteRunnerStatus,
} from "@entities/runner";

/** Локальный провайдер, который можно открыть облаку (ollama или openai_compat). */
export type CloudModelCandidate = {
  providerId: string;
  name: string;
  flavor: "ollama" | "openai";
  url: string;
  /** Имя по умолчанию: ollama у управляемой Ollama, иначе слаг имени провайдера. */
  defaultName: string;
};

export type RemoteRunnerViewProps = {
  status: RemoteRunnerStatus;
  candidates: readonly CloudModelCandidate[];
  now: number;
  /** Идёт запрос: управление занято. */
  busy?: boolean;
  /** Текст отказа последнего действия. */
  error?: string | null;
  /** Текст причины для состояния error и offline (по detail_code). */
  detailText?: string | null;
  /** Имя машины по умолчанию: имя компьютера. */
  defaultName?: string;
  onToggle: (enabled: boolean) => void;
  onPair: (serverUrl: string, name: string) => void;
  onToken: (serverUrl: string, token: string) => void;
  onCancelPairing: () => void;
  onUnpair: () => void;
  onConcurrency: (value: number) => void;
  onYield: (value: boolean) => void;
  onModels: (choices: { name: string; provider_id: string }[]) => void;
};

const CONCURRENCY = [1, 2, 3, 4] as const;
const MS_PER_MINUTE = 60_000;
const MS_PER_SECOND = 1000;

const countdown = (expiresAt: string, now: number): string | null => {
  const left = Date.parse(expiresAt) - now;
  if (Number.isNaN(left) || left <= 0) return null;
  const minutes = Math.floor(left / MS_PER_MINUTE);
  const seconds = Math.floor((left % MS_PER_MINUTE) / MS_PER_SECOND);
  return `${String(minutes)}:${String(seconds).padStart(2, "0")}`;
};

/**
 * «Облачные сборки» локальной Студии: переключатель, подключение к серверу
 * кодом или токеном, состояние, проверки Docker и образа, настройки и модели,
 * которые Студия открывает облаку.
 */
export const RemoteRunnerView = ({
  status,
  candidates,
  now,
  busy = false,
  error = null,
  detailText = null,
  defaultName = "",
  onToggle,
  onPair,
  onToken,
  onCancelPairing,
  onUnpair,
  onConcurrency,
  onYield,
  onModels,
}: RemoteRunnerViewProps) => {
  const { t } = useTranslation("runners");
  const uid = useId();
  const needsPairing =
    status.enabled &&
    (status.state === "unpaired" ||
      status.state === "revoked" ||
      (!status.paired && status.state !== "pairing"));

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="remote-runner"
    >
      <div
        id="remote-runner"
        className="settings-anchor flex flex-col"
        style={{ gap: 4 }}
      >
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
          {t("remote.title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>
          {t("remote.sub")}
        </p>
      </div>

      <Section>
        <SettingRow
          label={t("remote.toggle")}
          hint={t("remote.toggleHint")}
          htmlFor={`${uid}-toggle`}
        >
          <Switch
            id={`${uid}-toggle`}
            checked={status.enabled}
            disabled={busy}
            onChange={onToggle}
            testId="remote-runner-toggle"
          />
        </SettingRow>
      </Section>

      {(status.enabled || status.paired) && (
        <StateLine status={status} detailText={detailText} />
      )}

      {error && <Notice tone="err" role="alert" text={error} />}

      {needsPairing && (
        <PairForm
          serverUrl={status.server_url ?? ""}
          name={status.runner_name ?? defaultName}
          busy={busy}
          onPair={onPair}
          onToken={onToken}
        />
      )}

      {status.state === "pairing" && status.pairing && (
        <PairingCode
          pairing={status.pairing}
          now={now}
          busy={busy}
          onCancel={onCancelPairing}
        />
      )}

      {status.paired && (
        <>
          {status.docker === "missing" && (
            <Notice tone="warn" text={t("remote.checks.docker")} />
          )}
          {status.docker === "ok" && status.tex_image === "missing" && (
            <Notice
              tone="warn"
              text={t("remote.checks.image")}
              action={
                <Link
                  to="/settings/compiler"
                  className="btn xs"
                  style={{ textDecoration: "none" }}
                >
                  {t("remote.checks.toImages")}
                </Link>
              }
            />
          )}
          <Section>
            <SettingRow
              label={t("remote.concurrency")}
              hint={t("remote.concurrencyHint")}
              testId="remote-runner-concurrency"
            >
              <div
                className="seg"
                role="radiogroup"
                aria-label={t("remote.concurrency")}
              >
                {CONCURRENCY.map((n) => (
                  <button
                    key={n}
                    type="button"
                    role="radio"
                    aria-checked={status.concurrency === n}
                    className={status.concurrency === n ? "active" : undefined}
                    disabled={busy}
                    onClick={() => {
                      onConcurrency(n);
                    }}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </SettingRow>
            <SettingRow
              label={t("remote.yield")}
              hint={t("remote.yieldHint")}
              htmlFor={`${uid}-yield`}
            >
              <Switch
                id={`${uid}-yield`}
                checked={status.yield_to_local}
                disabled={busy}
                onChange={onYield}
                testId="remote-runner-yield"
              />
            </SettingRow>
          </Section>
          <CloudModels
            status={status}
            candidates={candidates}
            busy={busy}
            onModels={onModels}
          />
          <div>
            <Button
              type="button"
              variant="ghost"
              onClick={onUnpair}
              disabled={busy}
              style={{ color: "var(--c-err)" }}
              data-testid="remote-runner-unpair"
            >
              {t("remote.unpair")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
};

const StateLine = ({
  status,
  detailText,
}: {
  status: RemoteRunnerStatus;
  detailText: string | null;
}) => {
  const { t } = useTranslation("runners");
  const text =
    status.state === "error"
      ? t("remote.state.error", {
          reason: detailText ?? status.detail_code ?? "",
        })
      : t(`remote.state.${status.state}`);
  return (
    <div
      className="flex items-center"
      style={{
        gap: 12,
        padding: "10px 14px",
        borderRadius: "var(--r-3)",
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
        flexWrap: "wrap",
      }}
      data-testid="remote-runner-state"
      data-state={status.state}
    >
      <StatusDot status={REMOTE_STATE_DOT[status.state]} label={text} />
      {status.paired && status.server_url && (
        <span className="dim" style={{ fontSize: 12 }}>
          <Laptop
            size={12}
            aria-hidden="true"
            style={{ verticalAlign: -2, marginRight: 4 }}
          />
          {t("remote.connectedTo", {
            server: status.server_url.replace(/^https?:\/\//, ""),
            name: status.runner_name ?? "",
          })}
        </span>
      )}
      {status.running_jobs > 0 && (
        <span className="chip sans" style={{ fontSize: 11 }}>
          {t("remote.running", { count: status.running_jobs })}
        </span>
      )}
      {status.state === "offline" && detailText && (
        <span className="dim" style={{ fontSize: 12 }}>
          {detailText}
        </span>
      )}
    </div>
  );
};

const PairForm = ({
  serverUrl,
  name,
  busy,
  onPair,
  onToken,
}: {
  serverUrl: string;
  name: string;
  busy: boolean;
  onPair: (serverUrl: string, name: string) => void;
  onToken: (serverUrl: string, token: string) => void;
}) => {
  const { t } = useTranslation("runners");
  const [url, setUrl] = useState(serverUrl);
  const [machine, setMachine] = useState(name);
  const [withToken, setWithToken] = useState(false);
  const [token, setToken] = useState("");
  const [tried, setTried] = useState(false);
  const urlOk = isValidServerUrl(url);
  const tokenOk = token.trim().startsWith("hsrt_");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!urlOk) return;
    if (withToken) {
      if (tokenOk) onToken(url.trim(), token.trim());
      return;
    }
    onPair(url.trim(), machine.trim());
  };

  return (
    <form
      className="flex flex-col"
      style={{ gap: 12 }}
      noValidate
      onSubmit={submit}
      data-testid="remote-runner-pair-form"
    >
      <Input
        label={t("remote.serverUrl")}
        hint={t("remote.serverUrlHint")}
        value={url}
        placeholder="https://studio.example.org"
        inputMode="url"
        autoComplete="url"
        {...(tried && !urlOk ? { error: t("remote.serverUrlInvalid") } : {})}
        onChange={(event) => {
          setUrl(event.target.value);
        }}
        data-testid="remote-runner-server-url"
      />
      {withToken ? (
        <Input
          label={t("remote.token")}
          hint={t("remote.tokenHint")}
          value={token}
          // Токен секретный, как ключ ИИ-провайдера: не виден на экране и в
          // демонстрации экрана, пока его вводят.
          type="password"
          isMono
          autoComplete="off"
          spellCheck={false}
          {...(tried && !tokenOk ? { error: t("remote.tokenInvalid") } : {})}
          onChange={(event) => {
            setToken(event.target.value);
          }}
          data-testid="remote-runner-token-input"
        />
      ) : (
        <Input
          label={t("remote.name")}
          hint={t("remote.nameHint")}
          value={machine}
          maxLength={128}
          onChange={(event) => {
            setMachine(event.target.value);
          }}
          data-testid="remote-runner-name"
        />
      )}
      <div className="flex items-center" style={{ gap: 10, flexWrap: "wrap" }}>
        <Button
          type="submit"
          disabled={busy}
          data-testid={
            withToken ? "remote-runner-use-token" : "remote-runner-pair"
          }
        >
          {busy && <Spinner size="sm" />}
          <Cloud size={13} aria-hidden="true" />
          {withToken ? t("remote.useToken") : t("remote.pair")}
        </Button>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => {
            setWithToken((v) => !v);
            setTried(false);
          }}
          data-testid="remote-runner-have-token"
        >
          {withToken ? t("remote.hideToken") : t("remote.haveToken")}
        </button>
      </div>
    </form>
  );
};

const PairingCode = ({
  pairing,
  now,
  busy,
  onCancel,
}: {
  pairing: NonNullable<RemoteRunnerStatus["pairing"]>;
  now: number;
  busy: boolean;
  onCancel: () => void;
}) => {
  const { t } = useTranslation("runners");
  const left = countdown(pairing.expires_at, now);
  return (
    <div
      className="flex flex-col"
      style={{
        gap: 12,
        padding: 18,
        borderRadius: "var(--r-3)",
        border: "1px solid var(--accent)",
        background: "var(--bg-1)",
      }}
      data-testid="remote-runner-pairing"
    >
      <strong style={{ fontSize: 13 }}>{t("remote.code.title")}</strong>
      <span className="dim" style={{ fontSize: 12 }}>
        {t("remote.code.lead")}
      </span>
      <span
        className="mono"
        style={{
          fontSize: 28,
          fontWeight: 600,
          letterSpacing: "0.14em",
          color: "var(--fg-0)",
        }}
        data-testid="remote-runner-user-code"
      >
        {pairing.user_code}
      </span>
      <span
        className="dim"
        style={{ fontSize: 12 }}
        data-testid="remote-runner-code-countdown"
      >
        {left === null
          ? t("remote.code.expired")
          : t("remote.code.expires", { time: left })}
      </span>
      <div className="flex items-center" style={{ gap: 10, flexWrap: "wrap" }}>
        <a
          href={pairing.verification_uri_complete}
          target="_blank"
          rel="noreferrer"
          className="btn primary"
          style={{ textDecoration: "none", gap: 6 }}
          data-testid="remote-runner-open-verification"
        >
          <ExternalLink size={13} aria-hidden="true" />
          {t("remote.code.open")}
        </a>
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={busy}
          data-testid="remote-runner-cancel-pairing"
        >
          {t("remote.code.cancel")}
        </Button>
      </div>
    </div>
  );
};

const CloudModels = ({
  status,
  candidates,
  busy,
  onModels,
}: {
  status: RemoteRunnerStatus;
  candidates: readonly CloudModelCandidate[];
  busy: boolean;
  onModels: (choices: { name: string; provider_id: string }[]) => void;
}) => {
  const { t } = useTranslation("runners");
  const chosen = new Map(
    status.ai_endpoints.map((e) => [e.provider_id, e.name]),
  );
  const [names, setNames] = useState<Record<string, string>>({});
  const nameOf = (c: CloudModelCandidate): string =>
    names[c.providerId] ?? chosen.get(c.providerId) ?? c.defaultName;

  const save = (next: Map<string, string>) => {
    onModels([...next].map(([provider_id, name]) => ({ provider_id, name })));
  };

  return (
    <Section
      title={t("remote.models.title")}
      description={t("remote.models.lead")}
      testId="remote-runner-models"
    >
      {candidates.length === 0 ? (
        <p className="dim" style={{ margin: 0, fontSize: 12 }}>
          {t("remote.models.empty")}
        </p>
      ) : (
        <ul
          className="flex flex-col"
          style={{ gap: 10, listStyle: "none", margin: 0, padding: 0 }}
        >
          {candidates.map((c) => {
            const on = chosen.has(c.providerId);
            const name = nameOf(c);
            const nameOk = isValidEndpointName(name);
            return (
              <li
                key={c.providerId}
                className="flex items-center"
                style={{ gap: 12, flexWrap: "wrap" }}
                data-testid={`remote-runner-ai-endpoint-${c.defaultName}`}
                data-on={on ? "true" : undefined}
              >
                <label
                  className="flex items-center"
                  style={{ gap: 8, minWidth: 220, flex: 1 }}
                >
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={busy || (!on && !nameOk)}
                    aria-label={`${t("remote.models.open")}: ${c.name}`}
                    onChange={() => {
                      const next = new Map(chosen);
                      if (on) next.delete(c.providerId);
                      else next.set(c.providerId, name);
                      save(next);
                    }}
                  />
                  <span
                    className="flex flex-col"
                    style={{ gap: 2, minWidth: 0 }}
                  >
                    <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                      {c.name}
                      <span className="dim" style={{ fontWeight: 400 }}>
                        {" · "}
                        {t(`remote.models.flavor.${c.flavor}`)}
                      </span>
                    </span>
                    <span className="dim mono" style={{ fontSize: 11 }}>
                      {c.url}
                    </span>
                  </span>
                </label>
                <div style={{ width: 180 }}>
                  <Input
                    aria-label={`${t("remote.models.name")}: ${c.name}`}
                    value={name}
                    isMono
                    disabled={busy}
                    {...(!nameOk
                      ? { error: t("remote.models.nameInvalid") }
                      : {})}
                    onChange={(event) => {
                      setNames((prev) => ({
                        ...prev,
                        [c.providerId]: event.target.value,
                      }));
                    }}
                    onBlur={() => {
                      // Имя уходит на сервер, только если адрес уже открыт и имя верное.
                      if (on && nameOk && chosen.get(c.providerId) !== name) {
                        const next = new Map(chosen);
                        next.set(c.providerId, name);
                        save(next);
                      }
                    }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
};
