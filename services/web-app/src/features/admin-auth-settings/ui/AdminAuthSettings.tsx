import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { ErrorState, Section, Spinner, TableSkeleton } from "@shared/ui";
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
import { AuthSettingsForm } from "./AuthSettingsForm";
import { OidcSection } from "./OidcSection";

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

const baseUrlOf = (): string =>
  typeof window === "undefined" ? "" : window.location.origin;

const input = (draft: OidcDraft) => ({
  label: draft.label,
  issuer: draft.issuer,
  client_id: draft.client_id,
  scopes: draft.scopes,
  enabled: draft.enabled,
  auto_provision: draft.auto_provision,
});

/** Скелет страницы на время первой загрузки: разделы той же высоты, что и настоящие. */
const SettingsSkeleton = () => (
  <div
    className="flex flex-col"
    style={{ gap: 16 }}
    role="status"
    data-testid="admin-settings-loading"
  >
    {[3, 1, 2].map((rows, i) => (
      <Section
        key={i}
        title={<span className="adm-skel" style={{ width: 160 }} />}
      >
        <TableSkeleton rows={rows} columns={2} framed={false} />
      </Section>
    ))}
  </div>
);

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

  if (!ready) {
    return (
      <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
        <Spinner size="sm" />
      </div>
    );
  }

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
    ).then((ok) => {
      if (ok) {
        toast.success(
          t(provider.enabled ? "oidc.disabledToast" : "oidc.enabledToast", {
            name: provider.label,
          }),
        );
      }
    });
  };

  const oidc = (
    <OidcSection
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
                draft.client_id !== provider.client_id ? draft.client_id : null,
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
  );

  const failed = registration.isError || auth.isError || smtp.isError;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16, flex: 1 }}
      data-testid="admin-auth-settings"
    >
      {registration.data && auth.data && smtp.data ? (
        <AuthSettingsForm
          registration={registration.data}
          auth={auth.data}
          smtp={smtp.data}
          oidc={oidc}
          saveRegistration={(patch) => saveRegistration.mutateAsync(patch)}
          saveAuth={(passwordEnabled) => saveAuth.mutateAsync(passwordEnabled)}
          saveSmtp={(patch) => {
            testSmtp.reset();
            return saveSmtp.mutateAsync(patch);
          }}
          onSaved={() => {
            toast.success(t("savedToast"));
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
      ) : failed ? (
        <ErrorState
          framed
          title={t("loadFailed")}
          description={t("loadFailedBody")}
          testId="admin-settings-failed"
          onRetry={() => {
            if (registration.isError) void registration.refetch();
            if (auth.isError) void auth.refetch();
            if (smtp.isError) void smtp.refetch();
          }}
        />
      ) : (
        <SettingsSkeleton />
      )}
    </div>
  );
};
