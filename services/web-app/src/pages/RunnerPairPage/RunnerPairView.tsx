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
} from "@shared/ui/DeviceCodeCard";
import {
  maskUserCode,
  normalizeUserCode,
  type RunnerPairingInfo,
} from "@entities/runner";

/** Итог страницы подтверждения: решение принято или код не годится. */
export type PairResult =
  "approved" | "denied" | "expired" | "invalid" | "used" | "disabled" | "limit";

export type RunnerPairViewState =
  | { kind: "enter" }
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "pending"; info: RunnerPairingInfo }
  | { kind: "result"; result: PairResult; info?: RunnerPairingInfo | null };

export type RunnerPairViewProps = {
  state: RunnerPairViewState;
  now: number;
  /** Идёт решение: кнопки заняты. */
  deciding?: "approve" | "deny" | null;
  onCode: (code: string) => void;
  onApprove: () => void;
  onDeny: () => void;
  onRetry?: () => void;
  onOtherCode: () => void;
};

const GOOD: readonly PairResult[] = ["approved"];
const NEUTRAL: readonly PairResult[] = ["denied", "used"];

/** Карточка подтверждения сопряжения: вход по коду, сведения, решение, итог. */
export const RunnerPairView = ({
  state,
  now,
  deciding = null,
  onCode,
  onApprove,
  onDeny,
  onRetry,
  onOtherCode,
}: RunnerPairViewProps) => {
  const { t } = useTranslation("runners");
  return (
    <DeviceCodeShell caption={t("pair.pageTitle")} testId="runner-pair-page">
      {state.kind === "enter" && <EnterCode onCode={onCode} />}
      {state.kind === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 13 }}
          data-testid="runner-pair-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("pair.loading")}</span>
        </div>
      )}
      {state.kind === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("pair.loadFailed")}
          action={
            onRetry && (
              <button type="button" className="btn xs" onClick={onRetry}>
                {t("retry")}
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
        <Result result={state.result} onOtherCode={onOtherCode} />
      )}
    </DeviceCodeShell>
  );
};

const EnterCode = ({ onCode }: { onCode: (code: string) => void }) => {
  const { t } = useTranslation("runners");
  const [code, setCode] = useState("");
  const [tried, setTried] = useState(false);
  const normalized = normalizeUserCode(code);
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
        <h1 style={{ margin: 0, fontSize: 18 }}>{t("pair.enterTitle")}</h1>
        <p className="dim" style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}>
          {t("pair.enterLead")}
        </p>
      </div>
      <Input
        label={t("connectDialog.studio.codeLabel")}
        value={code}
        placeholder="BCDF-2345"
        autoFocus
        autoComplete="off"
        spellCheck={false}
        className="mono"
        {...(tried && !normalized
          ? { error: t("connectDialog.studio.codeInvalid") }
          : {})}
        onChange={(event) => {
          setCode(maskUserCode(event.target.value));
        }}
        data-testid="runner-pair-code-input"
      />
      <div className="flex" style={{ justifyContent: "flex-end" }}>
        <Button type="submit" data-testid="runner-pair-code-continue">
          {t("pair.continue")}
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
  info: RunnerPairingInfo;
  now: number;
  deciding: "approve" | "deny" | null;
  onApprove: () => void;
  onDeny: () => void;
}) => {
  const { t } = useTranslation("runners");
  // Защита от фишинга кода устройства: ссылку с кодом мог прислать чужой человек.
  // Подключить можно, только подтвердив, что подключение начато на своей машине.
  const [mine, setMine] = useState(false);
  const left = deviceCountdown(info.expires_at, now);
  const KindIcon = info.host_kind === "desktop" ? Laptop : Terminal;
  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="runner-pair-pending"
    >
      <h1 style={{ margin: 0, fontSize: 18, lineHeight: 1.3 }}>
        {t("pair.question", { name: info.name })}
      </h1>
      <DeviceCodeDisplay
        code={info.user_code}
        title={t("pair.codeTitle")}
        hint={t("pair.codeHint")}
        testId="runner-pair-user-code"
      />
      <DeviceFacts>
        <DeviceFact label={t("pair.kind")}>
          <span className="flex items-center" style={{ gap: 6 }}>
            <KindIcon size={13} aria-hidden="true" />
            {t(`mine.kind.${info.host_kind}`)}
          </span>
        </DeviceFact>
        <DeviceFact label={t("pair.requested")}>
          {formatPastTime(info.requested_at, now)}
        </DeviceFact>
        {info.client_ip && (
          <DeviceFact label={t("pair.ip")}>
            <span className="mono">{info.client_ip}</span>
          </DeviceFact>
        )}
        <DeviceFact label={t("pair.expires")}>
          <span
            className="flex items-center mono"
            style={{ gap: 6 }}
            data-testid="runner-pair-countdown"
          >
            <Clock size={13} aria-hidden="true" />
            {left === null
              ? t("pair.expiredNow")
              : t("pair.expiresIn", { time: left })}
          </span>
        </DeviceFact>
      </DeviceFacts>
      <Notice
        tone="warn"
        text={
          info.client_ip
            ? `${t("pair.warning")} ${t("pair.warningIp", { ip: info.client_ip })}`
            : t("pair.warning")
        }
      />
      <label
        className="flex items-center"
        style={{ gap: 10, fontSize: 13, cursor: "pointer" }}
      >
        <Switch
          checked={mine}
          onChange={setMine}
          disabled={deciding !== null}
          testId="runner-pair-confirm-mine"
        />
        {t("pair.confirmMine")}
      </label>
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onDeny}
          disabled={deciding !== null}
          data-testid="runner-pair-deny"
        >
          {deciding === "deny" && <Spinner size="sm" />}
          {t("pair.deny")}
        </Button>
        <Button
          type="button"
          onClick={onApprove}
          disabled={deciding !== null || left === null || !mine}
          data-testid="runner-pair-approve"
        >
          {deciding === "approve" && <Spinner size="sm" />}
          {t("pair.approve")}
        </Button>
      </div>
    </div>
  );
};

const Result = ({
  result,
  onOtherCode,
}: {
  result: PairResult;
  onOtherCode: () => void;
}) => {
  const { t } = useTranslation("runners");
  const tone = GOOD.includes(result)
    ? "good"
    : result === "denied"
      ? "denied"
      : NEUTRAL.includes(result)
        ? "neutral"
        : "warn";
  const retryable = result === "expired" || result === "invalid";
  return (
    <DeviceResult
      tone={tone}
      title={t(`pair.result.${result}.title`)}
      body={t(`pair.result.${result}.body`)}
      testId="runner-pair-result"
      state={result}
      actions={
        <>
          {retryable && (
            <Button
              type="button"
              variant="ghost"
              onClick={onOtherCode}
              data-testid="runner-pair-other-code"
            >
              {t("pair.otherCode")}
            </Button>
          )}
          <Link
            to="/settings/runners"
            className="btn"
            style={{ textDecoration: "none" }}
            data-testid="runner-pair-to-runners"
          >
            {t("pair.toRunners")}
          </Link>
        </>
      }
    />
  );
};
