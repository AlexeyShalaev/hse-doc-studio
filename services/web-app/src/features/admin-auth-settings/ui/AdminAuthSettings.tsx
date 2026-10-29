import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useBootstrap, type AdminOidcProvider } from "@entities/session";
import {
  useAuthSettings,
  useCreateProvider,
  useDeleteProvider,
  useOidcProviders,
  useRegistrationSettings,
  useSmtpSettings,
  useTestSmtp,
  useUpdateAuth,
  useUpdateProvider,
  useUpdateRegistration,
  useUpdateSmtp,
} from "../api/adminSettingsQueries";
import type { Failure } from "../lib/failure";
import { ensureAdminSettingsLocales } from "../lib/locales";
import type { OidcDraft } from "../lib/validate";
import { OidcCard } from "./OidcCard";
import { RegistrationCard } from "./RegistrationCard";
import { SignInMethodsCard } from "./SignInMethodsCard";
import { SmtpCard } from "./SmtpCard";

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

const baseUrlOf = (): string =>
  typeof window === "undefined" ? "" : window.location.origin;

/**
 * Настройки входа в админке: регистрация, способы входа, провайдеры OIDC и
 * почта. Значения, заданные окружением, показаны только для чтения; секреты
 * принимаются на запись и не показываются.
 */
export const AdminAuthSettings = () => {
  const { t } = useTranslation("adminSettings");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void ensureAdminSettingsLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);

  const bootstrap = useBootstrap().data;
  const registration = useRegistrationSettings();
  const auth = useAuthSettings();
  const smtp = useSmtpSettings();
  const providers = useOidcProviders();
  const saveRegistration = useUpdateRegistration();
  const saveAuth = useUpdateAuth();
  const saveSmtp = useUpdateSmtp();
  const testSmtp = useTestSmtp();
  const create = useCreateProvider();
  const update = useUpdateProvider();
  const remove = useDeleteProvider();
  const [oidcFailure, setOidcFailure] = useState<Failure | null>(null);
  const [saved, setSaved] = useState({
    registration: false,
    auth: false,
    smtp: false,
  });
  // Каждое сохранение пересоздаёт форму: введённые секреты и черновик сбрасываются.
  const [rounds, setRounds] = useState({ registration: 0, auth: 0, smtp: 0 });
  const markSaved = (key: keyof typeof saved, value: boolean) => {
    setSaved((s) => ({ ...s, [key]: value }));
    if (value) setRounds((r) => ({ ...r, [key]: r[key] + 1 }));
  };

  if (!ready) {
    return (
      <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
        <Spinner size="sm" />
      </div>
    );
  }

  const failed = registration.isError || auth.isError || smtp.isError;
  const loadedMain = registration.data && auth.data && smtp.data;

  const input = (draft: OidcDraft) => ({
    label: draft.label,
    issuer: draft.issuer,
    client_id: draft.client_id,
    scopes: draft.scopes,
    enabled: draft.enabled,
    auto_provision: draft.auto_provision,
  });

  const run = async (action: () => Promise<unknown>): Promise<boolean> => {
    setOidcFailure(null);
    try {
      await action();
      return true;
    } catch (error) {
      setOidcFailure(asFailure(error));
      return false;
    }
  };

  const toggleProvider = (provider: AdminOidcProvider) => {
    void run(() =>
      update.mutateAsync({
        id: provider.id,
        body: {
          label: null,
          issuer: null,
          client_id: null,
          client_secret: null,
          scopes: null,
          enabled: !provider.enabled,
          auto_provision: null,
        },
      }),
    );
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14, maxWidth: 720 }}
      data-testid="admin-auth-settings"
    >
      {failed && !loadedMain && (
        <Notice
          tone="err"
          role="alert"
          text={t("loadFailed")}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void registration.refetch();
                void auth.refetch();
                void smtp.refetch();
              }}
            >
              {t("retry")}
            </button>
          }
        />
      )}
      {!loadedMain && !failed && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          data-testid="admin-settings-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("loading")}</span>
        </div>
      )}

      {registration.data && (
        <RegistrationCard
          key={`${JSON.stringify(registration.data)}:${String(rounds.registration)}`}
          settings={registration.data}
          smtpEnabled={
            smtp.data?.enabled ?? bootstrap?.auth.smtp_enabled ?? false
          }
          pending={saveRegistration.isPending}
          failure={
            saveRegistration.isError ? asFailure(saveRegistration.error) : null
          }
          saved={saved.registration}
          onSave={(patch) => {
            markSaved("registration", false);
            saveRegistration.mutate(patch, {
              onSuccess: () => {
                markSaved("registration", true);
                toast.success(t("registration.toast"));
              },
            });
          }}
        />
      )}

      {auth.data && (
        <SignInMethodsCard
          key={`${JSON.stringify(auth.data)}:${String(rounds.auth)}`}
          settings={auth.data}
          pending={saveAuth.isPending}
          failure={saveAuth.isError ? asFailure(saveAuth.error) : null}
          saved={saved.auth}
          onSave={(passwordEnabled) => {
            markSaved("auth", false);
            saveAuth.mutate(passwordEnabled, {
              onSuccess: () => {
                markSaved("auth", true);
              },
            });
          }}
        />
      )}

      <OidcCard
        status={
          providers.data ? "ready" : providers.isError ? "error" : "loading"
        }
        providers={providers.data ?? []}
        baseUrl={baseUrlOf()}
        saving={create.isPending || update.isPending}
        formFailure={oidcFailure}
        failure={oidcFailure}
        deleting={remove.isPending}
        onRetry={() => {
          void providers.refetch();
        }}
        onReset={() => {
          setOidcFailure(null);
        }}
        onCreate={(draft) =>
          run(() =>
            create.mutateAsync({
              ...input(draft),
              client_secret: draft.client_secret,
            }),
          )
        }
        onUpdate={(provider, draft) =>
          run(() =>
            update.mutateAsync({
              id: provider.id,
              body: {
                label: draft.label !== provider.label ? draft.label : null,
                issuer: draft.issuer !== provider.issuer ? draft.issuer : null,
                client_id:
                  draft.client_id !== provider.client_id
                    ? draft.client_id
                    : null,
                // Секрет уходит, только если его ввели заново.
                client_secret:
                  draft.client_secret !== "" ? draft.client_secret : null,
                scopes: draft.scopes !== provider.scopes ? draft.scopes : null,
                enabled:
                  draft.enabled !== provider.enabled ? draft.enabled : null,
                auto_provision:
                  draft.auto_provision !== provider.auto_provision
                    ? draft.auto_provision
                    : null,
              },
            }),
          )
        }
        onToggle={toggleProvider}
        onDelete={(provider) => run(() => remove.mutateAsync(provider.id))}
      />

      {smtp.data && (
        <SmtpCard
          key={`${JSON.stringify(smtp.data)}:${String(rounds.smtp)}`}
          settings={smtp.data}
          pending={saveSmtp.isPending}
          failure={saveSmtp.isError ? asFailure(saveSmtp.error) : null}
          saved={saved.smtp}
          onSave={(patch) => {
            markSaved("smtp", false);
            testSmtp.reset();
            saveSmtp.mutate(patch, {
              onSuccess: () => {
                markSaved("smtp", true);
              },
            });
          }}
          test={{
            pending: testSmtp.isPending,
            result: testSmtp.data ?? null,
            failure: testSmtp.isError ? asFailure(testSmtp.error) : null,
            ...(bootstrap?.user ? { defaultTo: bootstrap.user.email } : {}),
            onSend: (to) => {
              testSmtp.mutate(to);
            },
          }}
        />
      )}
    </div>
  );
};
