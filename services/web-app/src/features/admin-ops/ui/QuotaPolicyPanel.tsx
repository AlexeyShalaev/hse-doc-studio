import { useState } from "react";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Section, Select, SettingRow } from "@shared/ui";
import {
  KIND_ORDER,
  useQuotaPolicy,
  useSaveQuotaPolicy,
  type AdminQuotaPolicy,
  type OnExceed,
  type QuotaKind,
} from "@entities/quota";
import { failureKey, type Failure } from "../lib/failure";
import { ViewState } from "./parts";

const GIB = 1024 ** 3;
const ON_EXCEED: readonly OnExceed[] = ["deprioritize", "reject", "warn"];

type Draft = {
  values: Record<QuotaKind, { user: string; org: string }>;
  warn: string;
  onExceed: OnExceed;
};

/** Пределы хранятся в байтах, в форме место вводят в гигабайтах. */
const toField = (kind: QuotaKind, value: number | null): string => {
  if (value === null) return "";
  return kind === "storage"
    ? String(Number((value / GIB).toFixed(3)))
    : String(value);
};

const fromField = (kind: QuotaKind, text: string): number | null | "bad" => {
  if (text.trim() === "") return null;
  const n = Number(text.replace(",", "."));
  if (!Number.isFinite(n) || n <= 0) return "bad";
  const value = kind === "storage" ? Math.round(n * GIB) : n;
  return Number.isInteger(value) && value >= 1 && value <= 2 ** 53
    ? value
    : "bad";
};

const draftOf = (policy: AdminQuotaPolicy): Draft => ({
  values: Object.fromEntries(
    KIND_ORDER.map((kind) => {
      const row = policy.defaults.find((d) => d.kind === kind);
      return [
        kind,
        {
          user: toField(kind, row?.user ?? null),
          org: toField(kind, row?.org ?? null),
        },
      ];
    }),
  ) as Draft["values"],
  warn: String(policy.warn_percent),
  onExceed: policy.on_exceed,
});

/** Собрать тело запроса из формы; `null`, если где-то неверное число. */
export const policyFromDraft = (draft: Draft): AdminQuotaPolicy | null => {
  const defaults: AdminQuotaPolicy["defaults"] = [];
  for (const kind of KIND_ORDER) {
    const user = fromField(kind, draft.values[kind].user);
    const org = fromField(kind, draft.values[kind].org);
    if (user === "bad" || org === "bad") return null;
    defaults.push({ kind, user, org });
  }
  const warn = Number(draft.warn);
  if (!Number.isInteger(warn) || warn < 1 || warn > 100) return null;
  return { defaults, warn_percent: warn, on_exceed: draft.onExceed };
};

export type QuotaPolicyViewProps = {
  policy: AdminQuotaPolicy;
  saving?: boolean;
  saved?: boolean;
  failure?: Failure | null;
  onSave: (body: AdminQuotaPolicy) => void;
};

/** Умолчания установки по видам ресурсов, порог предупреждения и поведение при исчерпании. */
export const QuotaPolicyView = ({
  policy,
  saving = false,
  saved = false,
  failure = null,
  onSave,
}: QuotaPolicyViewProps) => {
  const { t } = useTranslation("adminQuotas");
  const initial = draftOf(policy);
  const [draft, setDraft] = useState<Draft>(initial);
  const [tried, setTried] = useState(false);
  const body = policyFromDraft(draft);
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);

  const setValue = (kind: QuotaKind, scope: "user" | "org", text: string) => {
    setDraft({
      ...draft,
      values: {
        ...draft.values,
        [kind]: { ...draft.values[kind], [scope]: text },
      },
    });
  };

  return (
    <>
      <Section
        title={t("adminOps:resources.title")}
        description={t("adminOps:resources.lead")}
        testId="quota-policy"
      >
        <div
          className="ops-resources"
          role="table"
          aria-label={t("adminOps:resources.title")}
        >
          <div className="ops-resources-row ops-resources-head" role="row">
            <span role="columnheader">{t("adminOps:resources.kind")}</span>
            <span role="columnheader">{t("adminOps:resources.perUser")}</span>
            <span role="columnheader">{t("adminOps:resources.perOrg")}</span>
          </div>
          {KIND_ORDER.map((kind) => (
            <div className="ops-resources-row" role="row" key={kind}>
              <span role="rowheader">
                <strong>{t(`adminOps:resources.kinds.${kind}.label`)}</strong>
                <span className="ops-resources-hint">
                  {t(`adminOps:resources.kinds.${kind}.hint`)}
                </span>
              </span>
              {(["user", "org"] as const).map((scope) => (
                <span key={scope} role="cell" className="ops-unit-field">
                  <Input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    value={draft.values[kind][scope]}
                    placeholder={t("quotas.unlimited")}
                    aria-label={`${t(`adminOps:resources.kinds.${kind}.label`)}: ${t(scope === "user" ? "resources.perUser" : "resources.perOrg")}`}
                    aria-invalid={
                      tried &&
                      fromField(kind, draft.values[kind][scope]) === "bad"
                        ? true
                        : undefined
                    }
                    onChange={(event) => {
                      setValue(kind, scope, event.target.value);
                    }}
                    data-testid={`policy-${kind}-${scope}`}
                  />
                  <span className="ops-unit">
                    {t(`adminOps:resources.kinds.${kind}.unit`)}
                  </span>
                </span>
              ))}
            </div>
          ))}
        </div>
      </Section>

      <Section
        title={t("adminOps:resources.behavior.title")}
        description={t("adminOps:resources.behavior.lead")}
        testId="quota-behavior"
        footer={
          <div className="flex items-center" style={{ gap: 12 }}>
            <Button
              size="sm"
              disabled={!changed || saving}
              onClick={() => {
                setTried(true);
                if (body) onSave(body);
              }}
              data-testid="quota-policy-save"
            >
              {t("adminOps:resources.save")}
            </Button>
            {changed && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDraft(initial);
                  setTried(false);
                }}
              >
                {t("adminOps:cancel")}
              </Button>
            )}
            {tried && !body && (
              <span
                role="alert"
                style={{ color: "var(--c-err)", fontSize: 12.5 }}
              >
                {t("adminOps:resources.invalid")}
              </span>
            )}
            {failure && (
              <span
                role="alert"
                style={{ color: "var(--c-err)", fontSize: 12.5 }}
              >
                {t(failureKey(failure.code))}
              </span>
            )}
            {saved && !changed && (
              <span
                role="status"
                className="flex items-center"
                style={{ gap: 6, fontSize: 12.5, color: "var(--c-ok)" }}
                data-testid="quota-policy-saved"
              >
                <Check size={14} aria-hidden="true" />
                {t("quotas.saved")}
              </span>
            )}
          </div>
        }
      >
        <SettingRow
          label={t("adminOps:resources.onExceed.label")}
          hint={t(`adminOps:resources.onExceed.hint.${draft.onExceed}`)}
          htmlFor="quota-on-exceed"
        >
          <Select
            id="quota-on-exceed"
            ariaLabel={t("adminOps:resources.onExceed.label")}
            value={draft.onExceed}
            onValueChange={(value) => {
              setDraft({ ...draft, onExceed: value as OnExceed });
            }}
            options={ON_EXCEED.map((value) => ({
              value,
              label: t(`adminOps:resources.onExceed.options.${value}`),
            }))}
          />
        </SettingRow>
        <SettingRow
          label={t("adminOps:resources.warn.label")}
          hint={t("adminOps:resources.warn.hint")}
          htmlFor="quota-warn"
        >
          <span className="ops-unit-field">
            <Input
              id="quota-warn"
              type="number"
              min={1}
              max={100}
              value={draft.warn}
              aria-label={t("adminOps:resources.warn.label")}
              onChange={(event) => {
                setDraft({ ...draft, warn: event.target.value });
              }}
              data-testid="policy-warn"
            />
            <span className="ops-unit">%</span>
          </span>
        </SettingRow>
      </Section>
    </>
  );
};

/** Данные и сохранение умолчаний по видам ресурсов. */
export const QuotaPolicyPanel = () => {
  const { t } = useTranslation("adminQuotas");
  const policy = useQuotaPolicy();
  const save = useSaveQuotaPolicy();
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const status = policy.isPending
    ? "loading"
    : policy.isError
      ? "error"
      : "ready";
  return (
    <>
      <ViewState
        status={status}
        errorText={t("adminOps:resources.loadFailed")}
        onRetry={() => void policy.refetch()}
        testId="quota-policy-state"
      />
      {policy.data && (
        <QuotaPolicyView
          key={JSON.stringify(policy.data)}
          policy={policy.data}
          saving={save.isPending}
          saved={saved}
          failure={failure}
          onSave={(body) => {
            setFailure(null);
            setSaved(false);
            save.mutate(body, {
              onSuccess: () => {
                setSaved(true);
              },
              onError: (error) => {
                setFailure({ code: failureCode(error) });
              },
            });
          }}
        />
      )}
    </>
  );
};
