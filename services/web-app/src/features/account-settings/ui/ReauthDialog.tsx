import { useId, useState } from "react";
import { FingerprintPattern, KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { failureKey, type Failure } from "../lib/failure";
import { ssoReauthUrl } from "../lib/ssoReauthUrl";

export type ReauthDialogProps = {
  open: boolean;
  /** У аккаунта есть пароль и вход по паролю включён. */
  hasPassword: boolean;
  /** Есть passkey, подходящий к этому адресу, и браузер умеет WebAuthn. */
  hasPasskey: boolean;
  /** Провайдеры единого входа: без пароля и passkey личность подтверждает новый вход. */
  providers: { id: string; label: string }[];
  pending?: boolean;
  failure?: Failure | null;
  onPassword: (password: string) => void;
  onPasskey: () => void;
  onCancel: () => void;
};

/** Подтверждение личности перед добавлением или удалением passkey. */
export const ReauthDialog = ({
  open,
  hasPassword,
  hasPasskey,
  providers,
  pending = false,
  failure = null,
  onPassword,
  onPasskey,
  onCancel,
}: ReauthDialogProps) => {
  const { t } = useTranslation("account");
  const uid = useId();
  const [password, setPassword] = useState("");
  const ssoOnly = !hasPassword && !hasPasskey;

  return (
    <Modal
      isOpen={open}
      onClose={onCancel}
      title={t("reauth.title")}
      description={t(ssoOnly ? "reauth.ssoBody" : "reauth.body")}
    >
      <div
        data-testid="reauth-dialog"
        className="flex flex-col"
        style={{ gap: "0.75rem", padding: "1rem 1.5rem 1.5rem" }}
      >
        {hasPasskey && (
          <Button
            type="button"
            data-testid="reauth-passkey"
            aria-disabled={pending}
            variant={hasPassword ? "secondary" : "primary"}
            onClick={() => {
              if (!pending) onPasskey();
            }}
            style={{ justifyContent: "center", gap: "0.5rem" }}
          >
            {pending ? (
              <Spinner size="sm" />
            ) : (
              <FingerprintPattern size="0.9375rem" aria-hidden="true" />
            )}
            {t("reauth.passkey")}
          </Button>
        )}

        {hasPassword && (
          <form
            className="flex flex-col"
            style={{ gap: "0.625rem" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!pending && password !== "") onPassword(password);
            }}
          >
            <Input
              id={`${uid}-password`}
              label={t("reauth.password")}
              type="password"
              autoComplete="current-password"
              autoFocus={!hasPasskey}
              data-testid="reauth-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
              }}
            />
            <Button
              type="submit"
              data-testid="reauth-submit"
              disabled={password === ""}
              aria-disabled={pending}
              style={{ justifyContent: "center", gap: "0.5rem" }}
            >
              {pending ? (
                <Spinner size="sm" />
              ) : (
                <KeyRound size="0.875rem" aria-hidden="true" />
              )}
              {t("reauth.submit")}
            </Button>
          </form>
        )}

        {ssoOnly && (
          <div className="flex flex-col" style={{ gap: "0.5rem" }}>
            {providers.map((provider) => (
              <Button key={provider.id} variant="secondary" asChild>
                <a
                  href={ssoReauthUrl(provider.id)}
                  data-testid={`reauth-sso-${provider.id}`}
                  style={{ justifyContent: "center", textDecoration: "none" }}
                >
                  {t("reauth.sso", { name: provider.label })}
                </a>
              </Button>
            ))}
            {providers.length === 0 && (
              <p
                style={{ margin: 0, fontSize: "0.75rem", color: "var(--fg-2)" }}
              >
                {t("reauth.signInAgain")}
              </p>
            )}
          </div>
        )}

        {failure && (
          <div data-testid="reauth-failure">
            <Notice
              tone="err"
              role="alert"
              text={t(failureKey(failure.code))}
            />
          </div>
        )}

        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("reauth.cancel")}
        </Button>
      </div>
    </Modal>
  );
};
