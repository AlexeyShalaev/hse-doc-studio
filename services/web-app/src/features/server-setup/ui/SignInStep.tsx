import { KeyRound, Mail, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Badge, Button } from "@shared/ui";
import type { SetupSettingKey } from "@entities/session";
import { isLocked } from "../lib/locked";
import type { SetupFailure } from "../model/useServerSetup";
import {
  FailureFrame,
  LockedBadge,
  PendingLabel,
  StepActions,
  StepHeading,
} from "./parts";

const Row = ({
  icon,
  title,
  body,
  badge,
  testId,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  badge: ReactNode;
  testId: string;
}) => (
  <li
    data-testid={testId}
    style={{
      display: "flex",
      gap: 12,
      alignItems: "flex-start",
      padding: "12px 14px",
      borderRadius: "var(--r-3)",
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
    }}
  >
    <span aria-hidden style={{ color: "var(--fg-2)", marginTop: 1 }}>
      {icon}
    </span>
    <span className="flex flex-col" style={{ gap: 2, flex: 1, minWidth: 0 }}>
      <span style={{ fontSize: 13.5, fontWeight: 500 }}>{title}</span>
      <span style={{ fontSize: 12.5, color: "var(--fg-2)" }}>{body}</span>
    </span>
    <span className="flex items-center" style={{ gap: 6 }}>
      {badge}
    </span>
  </li>
);

export type SignInStepProps = {
  passwordEnabled: boolean;
  locked: readonly SetupSettingKey[];
  smtpEnabled: boolean;
  pending?: boolean;
  failure?: SetupFailure | null;
  onBack: () => void;
  /** Записывает настройки входа и регистрации и ведёт к проверке окружения. */
  onSubmit: () => void;
};

/**
 * Шаг 4: способы входа. Пароль включён, единый вход и почта подключаются
 * позже в админке: без провайдера отключить пароли нельзя, иначе в установку
 * не войти никому.
 */
export const SignInStep = ({
  passwordEnabled,
  locked,
  smtpEnabled,
  pending = false,
  failure = null,
  onBack,
  onSubmit,
}: SignInStepProps) => {
  const { t } = useTranslation("auth");
  return (
    <section data-testid="setup-step-signin" aria-labelledby="setup-title">
      <StepHeading
        id="setup-title"
        title={t("setup.signin.title")}
        lead={t("setup.signin.lead")}
      />
      {failure && <FailureFrame failure={failure} />}
      <ul
        className="flex flex-col"
        style={{ listStyle: "none", margin: 0, padding: 0, gap: 8 }}
      >
        <Row
          testId="setup-signin-password"
          icon={<KeyRound size={16} />}
          title={t("setup.signin.password.title")}
          body={t(
            passwordEnabled
              ? "setup.signin.password.on"
              : "setup.signin.password.off",
          )}
          badge={
            <>
              {isLocked(locked, "password_enabled") && <LockedBadge />}
              <Badge variant={passwordEnabled ? "success" : "warning"}>
                {t(passwordEnabled ? "setup.state.on" : "setup.state.off")}
              </Badge>
            </>
          }
        />
        <Row
          testId="setup-signin-sso"
          icon={<ShieldCheck size={16} />}
          title={t("setup.signin.sso.title")}
          body={t("setup.signin.sso.body")}
          badge={<Badge>{t("setup.signin.sso.later")}</Badge>}
        />
        <Row
          testId="setup-signin-mail"
          icon={<Mail size={16} />}
          title={t("setup.signin.mail.title")}
          body={t(
            smtpEnabled ? "setup.signin.mail.on" : "setup.signin.mail.off",
          )}
          badge={
            <Badge variant={smtpEnabled ? "success" : "warning"}>
              {t(smtpEnabled ? "setup.state.on" : "setup.signin.mail.links")}
            </Badge>
          }
        />
      </ul>
      <StepActions
        onBack={onBack}
        primary={
          <Button
            type="button"
            aria-disabled={pending}
            style={{ gap: 8 }}
            onClick={() => {
              if (!pending) onSubmit();
            }}
            data-testid="setup-save"
          >
            <PendingLabel
              pending={pending}
              idle={t("setup.signin.save")}
              busy={t("setup.saving")}
            />
          </Button>
        }
      />
    </section>
  );
};
