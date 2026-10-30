import { useState } from "react";
import { KeyRound, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminSigningPolicy, SigningServerKeys } from "@entities/session";
import type { Failure } from "../lib/failure";
import { isLocked } from "../lib/locked";
import { HINT } from "../lib/styles";
import { LockedBadge, SettingsCard } from "./parts";
import { SaveRow } from "./SaveRow";

export type SigningPolicyCardProps = {
  policy: AdminSigningPolicy;
  pending?: boolean;
  failure?: Failure | null;
  saved?: boolean;
  onSave: (serverKeys: SigningServerKeys) => void;
};

const ALTERNATIVES = ["cryptopro", "upload"] as const;

/**
 * Политика ключей подписи. По умолчанию сервер секретные ключи не хранит;
 * выключение политики блокирует уже сохранённые ключи, но не стирает их.
 */
export const SigningPolicyCard = ({
  policy,
  pending = false,
  failure = null,
  saved = false,
  onSave,
}: SigningPolicyCardProps) => {
  const { t } = useTranslation("adminInstall");
  const [allowed, setAllowed] = useState(policy.server_keys === "allowed");
  const locked = isLocked(policy.fields, "signing.server_keys");
  const dirty = allowed !== (policy.server_keys === "allowed");
  const turningOn = dirty && allowed;
  const turningOff = dirty && !allowed;

  return (
    <SettingsCard
      id="admin-signing"
      testId="admin-signing"
      title={t("signing.title")}
      sub={t("signing.sub")}
      aside={
        <Badge
          variant={policy.server_keys === "allowed" ? "warning" : "subtle"}
          data-testid="signing-state"
        >
          {t(`signing.state.${policy.server_keys}`)}
        </Badge>
      }
    >
      <form
        noValidate
        className="flex flex-col"
        style={{ gap: 14 }}
        data-testid="signing-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty && !pending && !locked) {
            onSave(allowed ? "allowed" : "forbidden");
          }
        }}
      >
        <label className="flex" style={{ gap: 10, alignItems: "flex-start" }}>
          <input
            type="checkbox"
            checked={allowed}
            disabled={locked}
            onChange={(e) => {
              setAllowed(e.target.checked);
            }}
            style={{ marginTop: 3 }}
            data-testid="signing-toggle"
          />
          <span className="flex flex-col" style={{ gap: 2 }}>
            <span
              className="flex items-center"
              style={{ gap: 8, fontSize: 13, fontWeight: 500 }}
            >
              {t("signing.toggle")}
              {locked && <LockedBadge testId="locked-signing" />}
            </span>
            <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
              {t("signing.toggleHint")}
            </span>
          </span>
        </label>

        <p
          className="flex items-center"
          style={{ ...HINT, gap: 6 }}
          data-testid="signing-stored"
        >
          <KeyRound size={13} aria-hidden="true" />
          {t("signing.stored", { count: policy.stored_keys })}
        </p>

        <div className="flex flex-col" style={{ gap: 6 }}>
          <strong style={{ fontSize: 12.5 }}>{t("signing.risksTitle")}</strong>
          <p style={HINT}>{t("signing.risks")}</p>
          <strong style={{ fontSize: 12.5, marginTop: 4 }}>
            {t("signing.altTitle")}
          </strong>
          <ul style={{ ...HINT, paddingLeft: 18 }}>
            {ALTERNATIVES.map((key) => (
              <li key={key}>{t(`signing.alt.${key}`)}</li>
            ))}
          </ul>
        </div>

        {turningOn && <Notice tone="warn" text={t("signing.warnOn")} />}
        {turningOff && (
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
        {policy.server_keys === "forbidden" && policy.stored_keys > 0 && (
          <p
            className="flex items-center"
            style={{ ...HINT, gap: 6 }}
            data-testid="signing-blocked"
          >
            <ShieldAlert size={13} aria-hidden="true" />
            {t("signing.blocked", { count: policy.stored_keys })}
          </p>
        )}

        <SaveRow
          testId="signing"
          dirty={dirty}
          pending={pending}
          failure={failure}
          saved={saved}
          allLocked={locked}
        />
      </form>
    </SettingsCard>
  );
};
