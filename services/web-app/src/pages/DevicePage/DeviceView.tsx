import { useState, type FormEvent } from "react";
import { Clock, Laptop, Terminal } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { Button, Input, Spinner } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { Notice } from "@shared/ui/ConflictKit";
import {
  DeviceCodeDisplay,
  DeviceCodeShell,
  DeviceFact,
  DeviceFacts,
  DeviceResult,
  deviceCountdown,
  maskDeviceCode,
  normalizeDeviceCode,
  type DeviceResultTone,
} from "@shared/ui/DeviceCodeCard";
import type { DeviceAuthorizationInfo, GitScope } from "@entities/git-server";

/** Итог страницы /device: решение принято или код не годится. */
export type DeviceResultKind =
  "approved" | "denied" | "expired" | "invalid" | "used";

export type DeviceViewState =
  | { kind: "enter" }
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "pending"; info: DeviceAuthorizationInfo }
  | { kind: "result"; result: DeviceResultKind };

export type DeviceViewProps = {
  state: DeviceViewState;
  now: number;
  deciding?: "approve" | "deny" | null;
  onCode: (code: string) => void;
  onApprove: (scopes: GitScope[]) => void;
  onDeny: () => void;
  onRetry?: () => void;
  onOtherCode: () => void;
};

const TONE: Record<DeviceResultKind, DeviceResultTone> = {
  approved: "good",
  denied: "denied",
  used: "neutral",
  expired: "warn",
  invalid: "warn",
};

/** Подтверждение входа Студии в git сервера (раздел 10.11 спецификации). */
export const DeviceView = ({
  state,
  now,
  deciding = null,
  onCode,
  onApprove,
  onDeny,
  onRetry,
  onOtherCode,
}: DeviceViewProps) => {
  const { t } = useTranslation("gitServer");
  return (
    <DeviceCodeShell caption={t("device.pageTitle")} testId="device-page">
      {state.kind === "enter" && <EnterCode onCode={onCode} />}
      {state.kind === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 13 }}
          data-testid="device-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("device.loading")}</span>
        </div>
      )}
      {state.kind === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("device.loadFailed")}
          action={
            onRetry && (
              <button type="button" className="btn xs" onClick={onRetry}>
                {t("device.retry")}
              </button>
            )
          }
        />
      )}
      {state.kind === "pending" && (
        <Pending
          info={state.info}
          now={now}
          deciding={deciding}
          onApprove={onApprove}
          onDeny={onDeny}
        />
      )}
      {state.kind === "result" && (
        <DeviceResult
          tone={TONE[state.result]}
          title={t(`device.result.${state.result}.title`)}
          body={t(`device.result.${state.result}.body`)}
          testId="device-result"
          state={state.result}
          actions={
            <>
              {(state.result === "expired" || state.result === "invalid") && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={onOtherCode}
                  data-testid="device-other-code"
                >
                  {t("device.otherCode")}
                </Button>
              )}
              <Link
                to="/settings/account#account-tokens"
                className="btn"
                style={{ textDecoration: "none" }}
                data-testid="device-to-tokens"
              >
                {t("device.toTokens")}
              </Link>
            </>
          }
        />
      )}
    </DeviceCodeShell>
  );
};

const EnterCode = ({ onCode }: { onCode: (code: string) => void }) => {
  const { t } = useTranslation("gitServer");
  const [code, setCode] = useState("");
  const [tried, setTried] = useState(false);
  const normalized = normalizeDeviceCode(code);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (normalized) onCode(normalized);
  };
  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      onSubmit={submit}
    >
      <div className="flex flex-col" style={{ gap: 6 }}>
        <h1 style={{ margin: 0, fontSize: 18 }}>{t("device.enterTitle")}</h1>
        <p className="dim" style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>
          {t("device.enterLead")}
        </p>
      </div>
      <Input
        label={t("device.codeLabel")}
        value={code}
        placeholder="BCDF-2345"
        autoFocus
        autoComplete="off"
        spellCheck={false}
        className="mono"
        {...(tried && !normalized ? { error: t("device.codeInvalid") } : {})}
        onChange={(event) => {
          setCode(maskDeviceCode(event.target.value));
        }}
        data-testid="device-code-input"
      />
      <div className="flex" style={{ justifyContent: "flex-end" }}>
        <Button type="submit" data-testid="device-code-continue">
          {t("device.continue")}
        </Button>
      </div>
    </form>
  );
};

const Pending = ({
  info,
  now,
  deciding,
  onApprove,
  onDeny,
}: {
  info: DeviceAuthorizationInfo;
  now: number;
  deciding: "approve" | "deny" | null;
  onApprove: (scopes: GitScope[]) => void;
  onDeny: () => void;
}) => {
  const { t } = useTranslation("gitServer");
  const writeRequested = info.requested_scopes.includes("git:write");
  const [write, setWrite] = useState(writeRequested);
  const left = deviceCountdown(info.expires_at, now);
  const KindIcon = info.client_kind === "desktop" ? Laptop : Terminal;
  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="device-card"
    >
      <h1 style={{ margin: 0, fontSize: 18, lineHeight: 1.3 }}>
        {t("device.question", { name: info.client_name })}
      </h1>
      <DeviceCodeDisplay
        code={info.user_code}
        title={t("device.codeTitle")}
        hint={t("device.codeHint")}
        testId="device-user-code"
      />
      <DeviceFacts>
        <DeviceFact label={t("device.kind")}>
          <span className="flex items-center" style={{ gap: 6 }}>
            <KindIcon size={13} aria-hidden="true" />
            {t(`device.kindValue.${info.client_kind}`)}
          </span>
        </DeviceFact>
        <DeviceFact label={t("device.requested")}>
          {formatPastTime(info.requested_at, now)}
        </DeviceFact>
        {info.client_ip && (
          <DeviceFact label={t("device.ip")}>
            <span className="mono">{info.client_ip}</span>
          </DeviceFact>
        )}
        <DeviceFact label={t("device.expires")}>
          <span
            className="flex items-center mono"
            style={{ gap: 6 }}
            data-testid="device-countdown"
          >
            <Clock size={13} aria-hidden="true" />
            {left === null
              ? t("device.expiredNow")
              : t("device.expiresIn", { time: left })}
          </span>
        </DeviceFact>
      </DeviceFacts>
      <fieldset
        className="flex flex-col"
        style={{ gap: 10, border: 0, margin: 0, padding: 0 }}
        data-testid="device-scopes"
      >
        <legend style={{ fontSize: 12.5, fontWeight: 500, marginBottom: 6 }}>
          {t("device.scopesTitle")}
        </legend>
        <label className="flex items-start" style={{ gap: 10, fontSize: 13 }}>
          <Switch checked onChange={() => undefined} disabled />
          <span className="flex flex-col" style={{ gap: 2 }}>
            <span>{t("device.scopeRead")}</span>
            <span className="dim" style={{ fontSize: 12 }}>
              {t("device.scopeReadHint")}
            </span>
          </span>
        </label>
        <label className="flex items-start" style={{ gap: 10, fontSize: 13 }}>
          <Switch
            checked={write}
            onChange={setWrite}
            disabled={!writeRequested || deciding !== null}
            testId="device-scope-write"
          />
          <span className="flex flex-col" style={{ gap: 2 }}>
            <span>{t("device.scopeWrite")}</span>
            <span className="dim" style={{ fontSize: 12 }}>
              {t("device.scopeWriteHint")}
            </span>
          </span>
        </label>
      </fieldset>
      <Notice tone="warn" text={t("device.warning")} />
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onDeny}
          disabled={deciding !== null}
          data-testid="device-deny"
        >
          {deciding === "deny" && <Spinner size="sm" />}
          {t("device.deny")}
        </Button>
        <Button
          type="button"
          onClick={() => {
            onApprove(write ? ["git:read", "git:write"] : ["git:read"]);
          }}
          disabled={deciding !== null || left === null}
          data-testid="device-approve"
        >
          {deciding === "approve" && <Spinner size="sm" />}
          {t("device.approve")}
        </Button>
      </div>
    </div>
  );
};
