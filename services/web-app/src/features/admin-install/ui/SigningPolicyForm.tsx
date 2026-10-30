import { useId, useState } from "react";
import { FileSignature, KeyRound, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import {
  ListRow,
  Section,
  SectionList,
  SettingRow,
  StatusDot,
  StickySaveBar,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import type { AdminSigningPolicy, SigningServerKeys } from "@entities/session";
import { failureKey } from "../lib/failure";

export type SigningPolicyFormProps = {
  policy: AdminSigningPolicy;
  /** Отказ сервера приходит отклонённым промисом. */
  onSave: (serverKeys: SigningServerKeys) => Promise<unknown>;
  onSaved?: () => void;
};

/**
 * Политика ключей подписи. По умолчанию сервер секретные ключи не хранит;
 * выключение политики блокирует уже сохранённые ключи, но не стирает их.
 */
export const SigningPolicyForm = ({
  policy,
  onSave,
  onSaved,
}: SigningPolicyFormProps) => {
  const { t } = useTranslation("adminInstall");
  const uid = useId();
  const serverAllowed = policy.server_keys === "allowed";
  const [allowed, setAllowed] = useState(serverAllowed);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // После сохранения черновик снова следует за сервером.
  const [synced, setSynced] = useState(policy);
  if (synced !== policy) {
    setSynced(policy);
    setAllowed(serverAllowed);
  }
  const dirty = allowed !== serverAllowed;
  const blocked = !serverAllowed && policy.stored_keys > 0;

  const save = async () => {
    if (!dirty || busy) return;
    setBusy(true);
    setFailure(null);
    try {
      await onSave(allowed ? "allowed" : "forbidden");
      onSaved?.();
    } catch (error) {
      setFailure(t(failureKey(failureCode(error))));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: 16, flex: 1 }}
      data-testid="signing-form"
    >
      <Section
        id="admin-signing"
        testId="admin-signing"
        title={t("signing.title")}
        description={t("signing.sub")}
        actions={
          <span data-testid="signing-state">
            <StatusDot
              status={serverAllowed ? "warning" : "success"}
              label={t(`signing.state.${policy.server_keys}`)}
            />
          </span>
        }
      >
        <SettingRow
          label={t("signing.toggle")}
          hint={t("signing.toggleHint")}
          htmlFor={`${uid}-toggle`}
        >
          <Switch
            id={`${uid}-toggle`}
            checked={allowed}
            onChange={setAllowed}
            testId="signing-toggle"
          />
        </SettingRow>
        {dirty && (
          <div className="adm-setting-extra">
            {allowed ? (
              <Notice tone="warn" text={t("signing.warnOn")} />
            ) : (
              <div data-testid="signing-warn-off">
                <Notice
                  tone="warn"
                  text={
                    policy.stored_keys > 0
                      ? t("signing.warnOffKeys", { count: policy.stored_keys })
                      : t("signing.warnOff")
                  }
                />
              </div>
            )}
          </div>
        )}
        <SettingRow
          label={t("signing.storedLabel")}
          hint={
            blocked ? (
              <span data-testid="signing-blocked">
                {t("signing.blocked", { count: policy.stored_keys })}
              </span>
            ) : (
              t("signing.storedHint")
            )
          }
        >
          <span
            className="flex items-center"
            style={{ gap: 8, fontSize: 13 }}
            data-testid="signing-stored"
          >
            <KeyRound
              size={14}
              aria-hidden="true"
              style={{ color: "var(--fg-2)" }}
            />
            <span style={{ fontVariantNumeric: "tabular-nums" }}>
              {t("signing.stored", { count: policy.stored_keys })}
            </span>
          </span>
        </SettingRow>
      </Section>

      <Section
        title={t("signing.considerTitle")}
        description={t("signing.considerSub")}
        flush
        testId="signing-consider"
      >
        <SectionList>
          <ListRow
            icon={<ShieldAlert size={15} />}
            tone="warning"
            title={t("signing.risksTitle")}
            description={t("signing.risks")}
          />
          <ListRow
            icon={<FileSignature size={15} />}
            tone="info"
            title={t("signing.altTitle")}
            description={
              <>
                {t("signing.alt.cryptopro")} {t("signing.alt.upload")}
              </>
            }
          />
        </SectionList>
      </Section>

      <StickySaveBar
        dirtyCount={dirty ? 1 : 0}
        busy={busy}
        error={failure}
        onSave={() => {
          void save();
        }}
        onDiscard={() => {
          setAllowed(serverAllowed);
          setFailure(null);
        }}
      />
    </div>
  );
};
