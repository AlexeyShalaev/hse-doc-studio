import { useId, useState, type FormEvent } from "react";
import { Laptop, Loader2, Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Button,
  CopyField,
  Input,
  Modal,
  SecretOnce,
  Spinner,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  RUNNER_TOKEN_TTLS,
  maskUserCode,
  normalizeUserCode,
  type CreateMyRunnerTokenRequest,
  type MyRunnerTokenCreated,
} from "@entities/runner";
import "./myRunners.css";

export type ConnectTab = "studio" | "server";

export type ConnectRunnerDialogProps = {
  isOpen: boolean;
  /** Вкладка при открытии (галерея). */
  initialTab?: ConnectTab;
  pending?: boolean;
  /** Текст отказа создания токена. */
  error?: string | null;
  /** Созданный токен: его секрет показывается один раз. */
  created?: MyRunnerTokenCreated | null;
  /** Перейти к подтверждению кода из Студии. */
  onPairCode: (code: string) => void;
  onCreateToken: (body: CreateMyRunnerTokenRequest) => void;
  onClose: () => void;
};

const DEFAULT_TTL = 24;
const LABEL_MAX = 128;

/**
 * «Подключить раннер»: Студия на компьютере (код устройства) или сервер в
 * консоли (разовый токен и команда запуска).
 */
export const ConnectRunnerDialog = ({
  isOpen,
  initialTab = "studio",
  pending = false,
  error = null,
  created = null,
  onPairCode,
  onCreateToken,
  onClose,
}: ConnectRunnerDialogProps) => {
  const { t } = useTranslation("runners");
  const [tab, setTab] = useState<ConnectTab>(created ? "server" : initialTab);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("connectDialog.title")}
      description={t("connectDialog.lead")}
      width={600}
    >
      {isOpen && (
        <div
          className="flex flex-col"
          style={{ gap: 16 }}
          data-testid="runner-connect-dialog"
        >
          <div
            role="tablist"
            aria-label={t("connectDialog.tabsLabel")}
            className="myr-tabs"
          >
            {(["studio", "server"] as const).map((id) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                data-testid={`runner-connect-tab-${id}`}
                onClick={() => {
                  setTab(id);
                }}
              >
                {id === "studio" ? (
                  <Laptop size={14} aria-hidden="true" />
                ) : (
                  <Terminal size={14} aria-hidden="true" />
                )}
                {id === "studio"
                  ? t("connectDialog.tabStudio")
                  : t("connectDialog.tabServer")}
              </button>
            ))}
          </div>
          <div role="tabpanel">
            {tab === "studio" ? (
              <StudioTab onPairCode={onPairCode} />
            ) : created ? (
              <TokenResult created={created} onClose={onClose} />
            ) : (
              <TokenForm
                pending={pending}
                error={error}
                onCancel={onClose}
                onSubmit={onCreateToken}
              />
            )}
          </div>
        </div>
      )}
    </Modal>
  );
};

const StudioTab = ({ onPairCode }: { onPairCode: (code: string) => void }) => {
  const { t } = useTranslation("runners");
  const id = useId();
  const [code, setCode] = useState("");
  const [tried, setTried] = useState(false);
  const normalized = normalizeUserCode(code);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (normalized) onPairCode(normalized);
  };

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      onSubmit={submit}
    >
      <ol className="myr-steps">
        <li>{t("connectDialog.studio.step1")}</li>
        <li>{t("connectDialog.studio.step2")}</li>
        <li>{t("connectDialog.studio.step3")}</li>
      </ol>
      <div className="flex items-end" style={{ gap: 8 }}>
        <div style={{ flex: 1 }}>
          <Input
            id={`${id}-code`}
            label={t("connectDialog.studio.codeLabel")}
            hint={t("connectDialog.studio.codeHint")}
            value={code}
            placeholder="BCDF-2345"
            autoComplete="off"
            spellCheck={false}
            className="myr-code-input"
            {...(tried && !normalized
              ? { error: t("connectDialog.studio.codeInvalid") }
              : {})}
            onChange={(event) => {
              setCode(maskUserCode(event.target.value));
            }}
            data-testid="runner-pair-code-input"
          />
        </div>
      </div>
      <div className="flex" style={{ justifyContent: "flex-end" }}>
        <Button type="submit" data-testid="runner-pair-code-continue">
          {t("connectDialog.studio.continue")}
        </Button>
      </div>
    </form>
  );
};

const TokenForm = ({
  pending,
  error,
  onCancel,
  onSubmit,
}: {
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (body: CreateMyRunnerTokenRequest) => void;
}) => {
  const { t } = useTranslation("runners");
  const [label, setLabel] = useState("");
  const [ttl, setTtl] = useState<number>(DEFAULT_TTL);

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      data-testid="runner-token-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ label: label.trim(), ttl_hours: ttl });
      }}
    >
      <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-1)" }}>
        {t("connectDialog.server.lead")}
      </p>
      <Input
        label={t("connectDialog.server.label")}
        hint={t("connectDialog.server.labelHint")}
        value={label}
        maxLength={LABEL_MAX}
        autoComplete="off"
        onChange={(event) => {
          setLabel(event.target.value);
        }}
        data-testid="runner-token-label"
      />
      <div className="flex flex-col" style={{ gap: 6 }}>
        <span className="form-label" id="runner-token-ttl">
          {t("connectDialog.server.ttl")}
        </span>
        <div
          className="seg seg-fill"
          role="radiogroup"
          aria-labelledby="runner-token-ttl"
        >
          {RUNNER_TOKEN_TTLS.map((hours) => (
            <button
              key={hours}
              type="button"
              role="radio"
              aria-checked={ttl === hours}
              className={ttl === hours ? "active" : undefined}
              data-testid={`runner-token-ttl-${String(hours)}`}
              onClick={() => {
                setTtl(hours);
              }}
            >
              {t(`connectDialog.server.ttlOption.${String(hours)}`)}
            </button>
          ))}
        </div>
      </div>
      {error && <Notice tone="err" role="alert" text={error} />}
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={pending}
        >
          {t("cancel")}
        </Button>
        <Button
          type="submit"
          disabled={pending}
          data-testid="runner-token-create-submit"
        >
          {pending && <Spinner size="sm" />}
          {t("connectDialog.server.submit")}
        </Button>
      </div>
    </form>
  );
};

const TokenResult = ({
  created,
  onClose,
}: {
  created: MyRunnerTokenCreated;
  onClose: () => void;
}) => {
  const { t } = useTranslation("runners");
  const [how, setHow] = useState<"command" | "docker">("command");
  return (
    <div data-testid="runner-token-secret">
      <SecretOnce
        label={t("connectDialog.server.secretLabel")}
        value={created.secret}
        hint={t("connectDialog.server.secretHint")}
        onClose={onClose}
        extra={
          <div
            className="flex flex-col"
            style={{
              gap: 8,
              paddingTop: 12,
              borderTop: "1px solid var(--border)",
            }}
          >
            <div className="seg" role="tablist">
              {(["command", "docker"] as const).map((id) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={how === id}
                  className={how === id ? "active" : undefined}
                  data-testid={`runner-token-how-${id}`}
                  onClick={() => {
                    setHow(id);
                  }}
                >
                  {id === "command"
                    ? t("connectDialog.server.commandTab")
                    : t("connectDialog.server.dockerTab")}
                </button>
              ))}
            </div>
            {how === "command" ? (
              <div data-testid="runner-token-command">
                <CopyField
                  value={created.command}
                  label={t("connectDialog.server.commandLabel")}
                  multiline
                  wrap="spaces"
                />
              </div>
            ) : (
              <div data-testid="runner-token-docker-command">
                <CopyField
                  value={created.docker_command}
                  label={t("connectDialog.server.dockerLabel")}
                  multiline
                  wrap="spaces"
                />
              </div>
            )}
            <p className="form-hint" style={{ margin: 0 }}>
              {how === "command"
                ? t("connectDialog.server.commandHint")
                : t("connectDialog.server.dockerHint")}
            </p>
            <p className="form-hint" style={{ margin: 0 }}>
              {t("connectDialog.server.aiHint")}
            </p>
            <span className="myr-waiting" role="status">
              <Loader2 size={13} className="animate-spin" aria-hidden="true" />
              {t("connectDialog.server.waiting")}
            </span>
          </div>
        }
      />
    </div>
  );
};
