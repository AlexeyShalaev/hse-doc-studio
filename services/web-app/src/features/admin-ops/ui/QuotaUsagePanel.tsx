import { useMemo, useState } from "react";
import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import type { PickerItem } from "@shared/lib";
import { Button, KpiTile, Picker, Section, Select } from "@shared/ui";
import { adminPickers } from "@entities/session";
import {
  KIND_ORDER,
  UsageList,
  formatBytes,
  formatCount,
  useOwnerUsage,
  useResetUsage,
  useUsageSummary,
  type OwnerKind,
  type QuotaKind,
} from "@entities/quota";
import type { Failure } from "../lib/failure";
import { FailureNotice } from "./parts";

const COUNTED: readonly QuotaKind[] = [
  "builds",
  "ai_tokens_day",
  "ai_tokens_month",
];

/** Итоги установки за период и просмотр использования любого человека или организации со сбросом счётчика. */
export const QuotaUsagePanel = () => {
  const { t, i18n } = useTranslation("adminOps");
  const quota = useTranslation("quota");
  const summary = useUsageSummary();
  const reset = useResetUsage();
  const [ownerKind, setOwnerKind] = useState<OwnerKind>("user");
  const [owner, setOwner] = useState<PickerItem | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const usage = useOwnerUsage(ownerKind, owner?.id ?? null);
  const source = useMemo(
    () => (ownerKind === "user" ? adminPickers.users() : adminPickers.orgs()),
    [ownerKind],
  );
  const units = quota.t("units.bytes", { returnObjects: true }) as string[];
  const total = (kind: QuotaKind): string => {
    const value = summary.data?.totals[kind];
    if (value === undefined) return "—";
    return kind === "storage"
      ? formatBytes(value, units, i18n.language)
      : formatCount(value, i18n.language);
  };

  return (
    <Section
      title={t("usageAdmin.title")}
      description={t("usageAdmin.lead", {
        date: summary.data?.period_start ?? "",
      })}
      testId="quota-usage"
    >
      <div className="ops-kpis" data-testid="usage-totals">
        {KIND_ORDER.filter((kind) => kind !== "members").map((kind) => (
          <KpiTile
            key={kind}
            label={quota.t(`kind.${kind}`)}
            value={total(kind)}
          />
        ))}
      </div>
      <div className="ops-override-form" data-testid="usage-owner-form">
        <Select
          ariaLabel={t("overrides.ownerKind.label")}
          value={ownerKind}
          onValueChange={(next) => {
            setOwnerKind(next as OwnerKind);
            setOwner(null);
          }}
          options={[
            { value: "user", label: t("overrides.ownerKind.user") },
            { value: "org", label: t("overrides.ownerKind.org") },
          ]}
        />
        <Picker
          source={source}
          value={owner}
          onChange={setOwner}
          label={t("usageAdmin.owner")}
          placeholder={t("usageAdmin.ownerPlaceholder")}
          testId="usage-owner"
        />
      </div>
      {failure && <FailureNotice failure={failure} />}
      {owner && usage.isError && (
        <p role="alert" style={{ color: "var(--c-err)" }}>
          {t("usageAdmin.loadFailed")}
        </p>
      )}
      {owner && usage.data && (
        <div data-testid="usage-owner-lines">
          <UsageList lines={usage.data.lines} />
          <div
            className="flex"
            style={{ gap: 8, flexWrap: "wrap", marginTop: 8 }}
          >
            {COUNTED.map((kind) => (
              <Button
                key={kind}
                size="sm"
                variant="ghost"
                disabled={reset.isPending}
                onClick={() => {
                  setFailure(null);
                  reset.mutate(
                    { owner_kind: ownerKind, owner_id: owner.id, kind },
                    {
                      onError: (error) =>
                        setFailure({ code: failureCode(error) }),
                    },
                  );
                }}
                data-testid={`usage-reset-${kind}`}
              >
                <RotateCcw size={13} aria-hidden="true" />
                {t("usageAdmin.reset", { kind: quota.t(`kindShort.${kind}`) })}
              </Button>
            ))}
          </div>
        </div>
      )}
    </Section>
  );
};
