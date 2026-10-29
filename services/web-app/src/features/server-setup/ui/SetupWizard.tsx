import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useThemeStore } from "@shared/lib";
import { Button, Spinner } from "@shared/ui";
import { ResultFrame } from "@shared/ui/ResultFrame";
import { draftFromSettings, draftIsValid, draftToBody } from "../lib/steps";
import type { SettingsDraft } from "../lib/steps";
import { useServerSetup } from "../model/useServerSetup";
import { AdminStep } from "./AdminStep";
import { DoneStep } from "./DoneStep";
import { EnvironmentStep } from "./EnvironmentStep";
import { LanguageStep } from "./LanguageStep";
import { OccupiedCard } from "./OccupiedCard";
import { RegistrationStep } from "./RegistrationStep";
import { SetupShell } from "./SetupShell";
import { SignInStep } from "./SignInStep";

const DEFAULT_DRAFT: SettingsDraft = {
  registration_mode: "invite",
  domains: "",
  require_approval: false,
  password_enabled: true,
};

const WizardLoading = () => (
  <div
    className="flex justify-center"
    style={{ padding: "32px 0" }}
    data-testid="auth-loading"
  >
    <Spinner />
  </div>
);

export type SetupWizardProps = {
  /** Форма входа администратора для нейтрального экрана: её подставляет страница. */
  signIn?: ReactNode;
};

/** /first-run: мастер первого запуска серверной установки, шаг за шагом. */
export const SetupWizard = ({ signIn = null }: SetupWizardProps) => {
  const { t } = useTranslation("auth");
  const lang = useThemeStore((s) => s.lang);
  const setLang = useThemeStore((s) => s.setLang);
  const m = useServerSetup();

  // Правки живут в форме, пока их нет, показываем действующие настройки сервера.
  const [edited, setDraft] = useState<SettingsDraft | null>(null);
  const serverSettings = m.settings.data;
  const shown =
    edited ??
    (serverSettings ? draftFromSettings(serverSettings) : DEFAULT_DRAFT);
  const locked = serverSettings?.locked_by_env ?? [];
  const patch = (change: Partial<SettingsDraft>) => {
    setDraft({ ...shown, ...change });
  };

  if (m.status.isError) {
    return (
      <section data-testid="setup-unavailable">
        <ResultFrame
          tone="err"
          role="alert"
          testId="setup-unavailable-frame"
          title={t("setup.unavailable.title")}
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                void m.status.refetch();
              }}
            >
              {t("setup.unavailable.retry")}
            </Button>
          }
        >
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
            {t("setup.unavailable.body")}
          </p>
        </ResultFrame>
      </section>
    );
  }
  if (!m.status.data) return <WizardLoading />;
  if (m.occupied) {
    return <OccupiedCard signedIn={m.user !== null} signIn={signIn} />;
  }
  if (m.step === null) return <WizardLoading />;
  // Без действующих настроек не показываем форму: иначе значения из окружения
  // мелькнули бы редактируемыми умолчаниями.
  if (
    (m.step === "registration" || m.step === "signin") &&
    m.settings.isPending &&
    m.settings.fetchStatus !== "idle"
  ) {
    return <WizardLoading />;
  }

  const busy =
    m.createAdmin.isPending ||
    m.applySettings.isPending ||
    m.complete.isPending;
  const { token_required: tokenRequired, steps_done: stepsDone } =
    m.status.data;
  const adminCreated = stepsDone.includes("admin") && m.isAdminSession;
  const failure = m.failure;

  const body = (() => {
    switch (m.step) {
      case "language":
        return <LanguageStep lang={lang} onLang={setLang} onNext={m.forward} />;
      case "admin":
        return (
          <AdminStep
            tokenRequired={tokenRequired}
            passwordMin={m.passwordMinLength}
            pending={m.createAdmin.isPending}
            failure={failure}
            created={
              adminCreated && m.user
                ? { name: m.user.name, email: m.user.email }
                : null
            }
            onSubmit={(input) => {
              m.createAdmin.mutate(input);
            }}
            onBack={m.back}
            onNext={m.forward}
          />
        );
      case "registration":
        return (
          <RegistrationStep
            draft={shown}
            locked={locked}
            onChange={patch}
            onBack={m.back}
            onNext={m.forward}
          />
        );
      case "signin":
        return (
          <SignInStep
            passwordEnabled={shown.password_enabled}
            locked={locked}
            smtpEnabled={m.smtpEnabled}
            pending={m.applySettings.isPending}
            failure={failure}
            onBack={m.back}
            onSubmit={() => {
              if (draftIsValid(shown))
                m.applySettings.mutate(draftToBody(shown));
            }}
          />
        );
      case "environment":
        return (
          <EnvironmentStep
            checks={m.environment.data?.checks ?? null}
            loading={m.environment.isFetching}
            loadFailed={m.environment.isError}
            completing={m.complete.isPending}
            failure={failure}
            onRecheck={() => {
              void m.environment.refetch();
            }}
            onBack={m.back}
            onComplete={() => {
              m.complete.mutate();
            }}
          />
        );
      case "done":
        return (
          <DoneStep smtpEnabled={m.smtpEnabled} onOpen={() => void m.open()} />
        );
    }
  })();

  return (
    <SetupShell step={m.step} busy={busy}>
      {body}
    </SetupShell>
  );
};
