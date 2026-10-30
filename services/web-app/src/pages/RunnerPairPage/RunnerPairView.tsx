import { useState, type FormEvent, type ReactNode } from "react";
import {
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock,
  Laptop,
  Link2,
  Terminal,
} from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { Button, Input, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
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

const MS_PER_MINUTE = 60_000;
const MS_PER_SECOND = 1000;

/** Оставшееся время кода: «8:42». */
const countdown = (expiresAt: string, now: number): string | null => {
  const left = Date.parse(expiresAt) - now;
  if (Number.isNaN(left) || left <= 0) return null;
  const minutes = Math.floor(left / MS_PER_MINUTE);
  const seconds = Math.floor((left % MS_PER_MINUTE) / MS_PER_SECOND);
  return `${String(minutes)}:${String(seconds).padStart(2, "0")}`;
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
    <main
      className="flex flex-1 items-center justify-center"
      style={{ padding: 24, overflowY: "auto" }}
      data-testid="runner-pair-page"
    >
      <section
        className="flex flex-col"
        style={{
          width: "min(520px, 100%)",
          gap: 16,
          padding: 24,
          border: "1px solid var(--border)",
          borderRadius: "var(--r-3)",
          background: "var(--bg-1)",
          boxShadow: "var(--shadow-1)",
        }}
      >
        <span
          className="flex items-center"
          style={{ gap: 8, fontSize: 12, color: "var(--fg-2)" }}
        >
          <Link2 size={14} aria-hidden="true" />
          {t("pair.pageTitle")}
        </span>
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
      </section>
    </main>
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

const Fact = ({ label, children }: { label: string; children: ReactNode }) => (
  <>
    <dt style={{ color: "var(--fg-2)" }}>{label}</dt>
    <dd style={{ margin: 0, color: "var(--fg-0)", overflowWrap: "anywhere" }}>
      {children}
    </dd>
  </>
);

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
  const left = countdown(info.expires_at, now);
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
      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          gap: "8px 16px",
          margin: 0,
          fontSize: 13,
        }}
      >
        <Fact label={t("pair.kind")}>
          <span className="flex items-center" style={{ gap: 6 }}>
            <KindIcon size={13} aria-hidden="true" />
            {t(`mine.kind.${info.host_kind}`)}
          </span>
        </Fact>
        <Fact label={t("pair.requested")}>
          {formatPastTime(info.requested_at, now)}
        </Fact>
        {info.client_ip && (
          <Fact label={t("pair.ip")}>
            <span className="mono">{info.client_ip}</span>
          </Fact>
        )}
        <Fact label={t("pair.expires")}>
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
        </Fact>
        <Fact label={t("connectDialog.studio.codeLabel")}>
          <span className="mono">{info.user_code}</span>
        </Fact>
      </dl>
      <Notice tone="warn" text={t("pair.warning")} />
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
          disabled={deciding !== null || left === null}
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
    ? "var(--c-ok)"
    : NEUTRAL.includes(result)
      ? "var(--fg-2)"
      : "var(--c-warn)";
  const Icon = GOOD.includes(result)
    ? CircleCheck
    : result === "denied"
      ? CircleX
      : CircleAlert;
  const retryable = result === "expired" || result === "invalid";
  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      role="status"
      data-testid="runner-pair-result"
      data-state={result}
    >
      <div className="flex items-start" style={{ gap: 12 }}>
        <Icon
          size={22}
          aria-hidden="true"
          style={{ color: tone, flexShrink: 0 }}
        />
        <div className="flex flex-col" style={{ gap: 4 }}>
          <h1 style={{ margin: 0, fontSize: 18 }}>
            {t(`pair.result.${result}.title`)}
          </h1>
          <p
            className="dim"
            style={{ margin: 0, fontSize: 13, lineHeight: 1.5 }}
          >
            {t(`pair.result.${result}.body`)}
          </p>
        </div>
      </div>
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
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
      </div>
    </div>
  );
};
