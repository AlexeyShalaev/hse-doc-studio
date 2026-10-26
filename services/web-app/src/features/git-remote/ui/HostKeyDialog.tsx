import { useEffect, useState } from "react";
import { ExternalLink, ShieldAlert, ShieldQuestion } from "lucide-react";
import { useTranslation } from "react-i18next";
import { REVEAL_FINGERPRINT, useTrustHost } from "@entities/git-remote";
import {
  describeGitError,
  readGitError,
  type GitHostKey,
} from "@entities/git-sync";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { CopyField } from "@shared/ui/CopyField";
import { Spinner } from "@shared/ui/Spinner";

export type HostKeyMode = "unknown" | "changed";

export type HostKeyDialogProps = {
  isOpen: boolean;
  mode: HostKeyMode;
  host: string;
  port: number | null;
  /** Ключи, которые сервер предъявил сейчас. */
  keys: GitHostKey[];
  /** Отпечатки, которым Студия доверяла раньше (для режима «изменился»). */
  knownFingerprints?: string[];
  onTrusted: () => void;
  onClose: () => void;
};

// Пауза перед кнопкой «Доверять»: отпечаток надо хотя бы прочитать.
export const TRUST_DELAY_S = 3;

// Где провайдер публикует отпечатки своих ключей.
const FINGERPRINT_DOCS: Record<string, string> = {
  "github.com":
    "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints",
  "gitlab.com":
    "https://docs.gitlab.com/user/gitlab_com/#ssh-known_hosts-entries",
  "bitbucket.org":
    "https://support.atlassian.com/bitbucket-cloud/docs/configure-ssh-and-two-step-verification/",
};

// Из набора ключей подтверждаем один: ssh отдаёт предпочтение ed25519.
const primaryKey = (keys: GitHostKey[]): GitHostKey | null =>
  keys.find((key) => key.type.includes("ed25519")) ?? keys[0] ?? null;

// Кнопка живёт внутри содержимого окна, поэтому отсчёт начинается заново при
// каждом показе: окно закрылось, кнопка размонтировалась.
const TrustButton = ({
  busy,
  disabled,
  onClick,
}: {
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
}) => {
  const { t } = useTranslation("gitAccess");
  const [seconds, setSeconds] = useState(TRUST_DELAY_S);
  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, []);
  const waiting = seconds > 0;
  return (
    <button
      type="button"
      className="btn primary"
      disabled={waiting || busy || disabled}
      onClick={onClick}
    >
      {busy && <Spinner size="sm" />}
      {waiting ? t("hostKey.trustWait", { seconds }) : t("hostKey.trust")}
    </button>
  );
};

const FingerprintList = ({ keys }: { keys: GitHostKey[] }) => {
  const { t } = useTranslation("gitAccess");
  return (
    <ul
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {keys.map((key) => (
        <li key={`${key.type}-${key.fingerprint_sha256}`}>
          <div className="dim" style={{ fontSize: 11, marginBottom: 3 }}>
            {key.type}
          </div>
          <CopyField
            value={key.fingerprint_sha256}
            label={t("hostKey.fingerprintOf", { type: key.type })}
          />
        </li>
      ))}
    </ul>
  );
};

// Подтверждение ключа сервера. Незнакомый сервер: показываем отпечаток и даём
// доверять после паузы. Ключ изменился: это может быть подмена, поэтому кнопка
// «Заменить» красная и работает только после ввода имени сервера.
export const HostKeyDialog = ({
  isOpen,
  mode: initialMode,
  host,
  port,
  keys,
  knownFingerprints = [],
  onTrusted,
  onClose,
}: HostKeyDialogProps) => {
  const { t } = useTranslation("gitAccess");
  const trust = useTrustHost();
  const [typedHost, setTypedHost] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState<{
    expected: string;
    actual: string;
  } | null>(null);
  // Проверка вернула «ключ изменился» без самих ключей: новый отпечаток
  // выясняем отдельным запросом, пока он неизвестен, заменить ключ нельзя.
  const [revealError, setRevealError] = useState<string | null>(null);
  const [revealAttempt, setRevealAttempt] = useState(0);

  // Окно остаётся смонтированным, когда его закрывает родитель после доверия:
  // состояние сбрасываем в момент закрытия, а не при следующем показе.
  const [wasOpen, setWasOpen] = useState(isOpen);
  if (wasOpen !== isOpen) {
    setWasOpen(isOpen);
    if (!isOpen) {
      setTypedHost("");
      setError(null);
      setChanged(null);
      setRevealError(null);
    }
  }

  const mode: HostKeyMode = changed ? "changed" : initialMode;
  const key = primaryKey(keys);
  const expected = changed?.expected ? [changed.expected] : knownFingerprints;
  const shownKeys =
    changed && keys.length === 0
      ? [{ type: "", fingerprint_sha256: changed.actual }]
      : keys;
  const needsReveal =
    initialMode === "changed" && keys.length === 0 && changed === null;
  const docs = FINGERPRINT_DOCS[host.toLowerCase()] ?? null;

  const { mutateAsync: trustAsync } = trust;
  useEffect(() => {
    if (!isOpen || !needsReveal) return;
    let cancelled = false;
    // Без `replace` сервер не меняет ключ, а отвечает 409 с тем, что видит сейчас.
    trustAsync({ host, port, fingerprint_sha256: REVEAL_FINGERPRINT })
      .then(() => {
        if (!cancelled) setRevealError(t("hostKey.revealFailed"));
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        const body = readGitError(caught);
        if (body?.code === "host_key_changed" && body.actual) {
          setChanged({ expected: body.expected ?? "", actual: body.actual });
          return;
        }
        setRevealError(describeGitError(caught, t("hostKey.revealFailed")));
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, needsReveal, revealAttempt, host, port, trustAsync, t]);

  const close = (): void => {
    setTypedHost("");
    setError(null);
    setChanged(null);
    setRevealError(null);
    onClose();
  };

  const confirm = async (): Promise<void> => {
    const fingerprint =
      key?.fingerprint_sha256 ??
      changed?.actual ??
      shownKeys[0]?.fingerprint_sha256;
    if (!fingerprint) {
      // Без отпечатка ничего не отправляем, но и молчать нельзя.
      setError(t("hostKey.noFingerprint"));
      setRevealError(null);
      setRevealAttempt((current) => current + 1);
      return;
    }
    setError(null);
    try {
      await trust.mutateAsync({
        host,
        port,
        fingerprint_sha256: fingerprint,
        ...(mode === "changed"
          ? { replace: true, confirm_host: typedHost.trim() }
          : {}),
      });
      setTypedHost("");
      onTrusted();
    } catch (caught) {
      const body = readGitError(caught);
      if (body?.code === "host_key_changed" && body.actual) {
        // Сервер уже известен, а ключ у него другой: переходим к замене.
        setChanged({ expected: body.expected ?? "", actual: body.actual });
        return;
      }
      setError(describeGitError(caught, t("hostKey.failed")));
    }
  };

  const isChanged = mode === "changed";
  const hasFingerprint = shownKeys.length > 0;
  const canReplace =
    hasFingerprint && typedHost.trim().toLowerCase() === host.toLowerCase();
  const Icon = isChanged ? ShieldAlert : ShieldQuestion;

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={600}
      title={
        <span className="flex items-center" style={{ gap: 8 }}>
          <Icon
            size={17}
            aria-hidden="true"
            style={{ color: isChanged ? "var(--c-err)" : "var(--c-warn)" }}
          />
          {isChanged
            ? t("hostKey.changedTitle", { host })
            : t("hostKey.unknownTitle", { host })}
        </span>
      }
      description={
        isChanged ? t("hostKey.changedText") : t("hostKey.unknownText")
      }
      footer={
        <>
          <button
            type="button"
            className="btn"
            autoFocus
            onClick={close}
            disabled={trust.isPending}
          >
            {t("hostKey.cancel")}
          </button>
          {isChanged ? (
            <button
              type="button"
              className="btn danger"
              disabled={!canReplace || trust.isPending}
              onClick={() => {
                void confirm();
              }}
            >
              {trust.isPending && <Spinner size="sm" />}
              {t("hostKey.replace")}
            </button>
          ) : (
            <TrustButton
              busy={trust.isPending}
              disabled={!key}
              onClick={() => {
                void confirm();
              }}
            />
          )}
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid={`host-key-${isChanged ? "changed" : "unknown"}`}
      >
        {isChanged ? (
          <>
            <Notice
              tone="err"
              role="alert"
              text={t("hostKey.changedWarning")}
            />
            {expected.length > 0 && (
              <div>
                <div
                  className="dim"
                  style={{ fontSize: 11.5, marginBottom: 4 }}
                >
                  {t("hostKey.before")}
                </div>
                <FingerprintList
                  keys={expected.map((fingerprint) => ({
                    type: "",
                    fingerprint_sha256: fingerprint,
                  }))}
                />
              </div>
            )}
            <div>
              <div className="dim" style={{ fontSize: 11.5, marginBottom: 4 }}>
                {t("hostKey.after")}
              </div>
              {hasFingerprint ? (
                <FingerprintList keys={shownKeys} />
              ) : revealError === null ? (
                <div
                  className="flex items-center dim"
                  role="status"
                  style={{ gap: 8, fontSize: 12.5 }}
                >
                  <Spinner size="sm" />
                  {t("hostKey.revealing")}
                </div>
              ) : (
                <Notice
                  tone="err"
                  role="alert"
                  text={revealError}
                  action={
                    <button
                      type="button"
                      className="btn xs"
                      onClick={() => {
                        setRevealError(null);
                        setRevealAttempt((current) => current + 1);
                      }}
                    >
                      {t("hostKey.retry")}
                    </button>
                  }
                />
              )}
            </div>
            <div className="field">
              <label htmlFor="host-key-confirm-host">
                {t("hostKey.typeHost", { host })}
              </label>
              <input
                id="host-key-confirm-host"
                type="text"
                className="input mono"
                value={typedHost}
                autoComplete="off"
                spellCheck={false}
                placeholder={host}
                onChange={(event) => {
                  setTypedHost(event.target.value);
                }}
              />
            </div>
          </>
        ) : (
          <>
            <FingerprintList keys={keys} />
            <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
              {t("hostKey.whereToCheck")}
            </p>
            {docs && (
              <a
                href={docs}
                target="_blank"
                rel="noopener noreferrer"
                className="btn sm"
                style={{
                  alignSelf: "flex-start",
                  gap: 6,
                  textDecoration: "none",
                }}
              >
                <ExternalLink size={12} aria-hidden="true" />
                {t("hostKey.openDocs", { host })}
              </a>
            )}
          </>
        )}
        {error && <Notice tone="err" role="alert" text={error} />}
      </div>
    </Modal>
  );
};
