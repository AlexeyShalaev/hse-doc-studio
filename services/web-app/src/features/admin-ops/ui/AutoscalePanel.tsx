import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Section, Select, SettingRow } from "@shared/ui";
import {
  useAutoscale,
  useSaveAutoscale,
  type AdminAutoscalePolicy,
  type AdminAutoscaleStatus,
  type AutoscaleMode,
} from "@entities/quota";
import { failureKey, type Failure } from "../lib/failure";
import { ViewState } from "./parts";

const MODES: readonly AutoscaleMode[] = ["off", "compose", "webhook"];

type NumField =
  | "min_runners"
  | "max_runners"
  | "target_queue_per_slot"
  | "scale_up_wait_s"
  | "cooldown_up_s"
  | "cooldown_down_s"
  | "idle_before_down_s"
  | "step_up"
  | "step_down";
const FIELDS: readonly NumField[] = [
  "min_runners",
  "max_runners",
  "target_queue_per_slot",
  "scale_up_wait_s",
  "cooldown_up_s",
  "cooldown_down_s",
  "idle_before_down_s",
  "step_up",
  "step_down",
];

type Draft = { mode: AutoscaleMode; url: string } & Record<NumField, string>;

const draftOf = (policy: AdminAutoscalePolicy): Draft => ({
  mode: policy.mode,
  url: policy.webhook_url ?? "",
  ...(Object.fromEntries(FIELDS.map((f) => [f, String(policy[f])])) as Record<
    NumField,
    string
  >),
});

/** Тело запроса из формы или `null`, если число вне границ. */
export const autoscaleFromDraft = (
  draft: Draft,
): AdminAutoscalePolicy | null => {
  const num = (field: NumField): number =>
    Number(draft[field].replace(",", "."));
  const body: AdminAutoscalePolicy = {
    mode: draft.mode,
    min_runners: num("min_runners"),
    max_runners: num("max_runners"),
    target_queue_per_slot: num("target_queue_per_slot"),
    scale_up_wait_s: num("scale_up_wait_s"),
    cooldown_up_s: num("cooldown_up_s"),
    cooldown_down_s: num("cooldown_down_s"),
    idle_before_down_s: num("idle_before_down_s"),
    step_up: num("step_up"),
    step_down: num("step_down"),
    webhook_url: draft.url.trim() === "" ? null : draft.url.trim(),
  };
  const ints = FIELDS.filter((f) => f !== "target_queue_per_slot").every(
    (f) => Number.isInteger(body[f]) && body[f] >= 0,
  );
  const okRange =
    body.max_runners >= Math.max(1, body.min_runners) &&
    body.max_runners <= 200 &&
    body.step_up >= 1 &&
    body.step_down >= 1 &&
    body.target_queue_per_slot >= 0.1 &&
    body.target_queue_per_slot <= 100;
  const okUrl =
    body.webhook_url === null || /^https?:\/\//.test(body.webhook_url);
  const okMode = body.mode !== "webhook" || body.webhook_url !== null;
  return ints && okRange && okUrl && okMode ? body : null;
};

export type AutoscaleViewProps = {
  status: AdminAutoscaleStatus;
  saving?: boolean;
  failure?: Failure | null;
  onSave: (body: AdminAutoscalePolicy) => void;
};

/** Политика, метрики очереди и последнее решение автомасштабирования раннеров. */
export const AutoscaleView = ({
  status,
  saving = false,
  failure = null,
  onSave,
}: AutoscaleViewProps) => {
  const { t, i18n } = useTranslation("adminRunners");
  const initial = draftOf(status.policy);
  const [draft, setDraft] = useState<Draft>(initial);
  const [tried, setTried] = useState(false);
  const body = autoscaleFromDraft(draft);
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);
  const m = status.metrics;
  const d = status.decision;
  const fmt = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString(i18n.language) : "—";

  return (
    <Section
      title={t("autoscale.title")}
      description={t("autoscale.lead")}
      testId="autoscale"
      footer={
        <div className="flex items-center" style={{ gap: "0.75rem" }}>
          <Button
            size="sm"
            disabled={!changed || saving}
            onClick={() => {
              setTried(true);
              if (body) onSave(body);
            }}
            data-testid="autoscale-save"
          >
            {t("adminOps:resources.save")}
          </Button>
          {tried && !body && (
            <span
              role="alert"
              style={{ color: "var(--c-err)", fontSize: "0.78125rem" }}
            >
              {t("autoscale.invalid")}
            </span>
          )}
          {failure && (
            <span
              role="alert"
              style={{ color: "var(--c-err)", fontSize: "0.78125rem" }}
            >
              {t(failureKey(failure.code))}
            </span>
          )}
        </div>
      }
    >
      <dl className="ops-facts" data-testid="autoscale-facts">
        <div>
          <dt>{t("autoscale.metrics.queue")}</dt>
          <dd data-testid="autoscale-queued">{m.queued}</dd>
        </div>
        <div>
          <dt>{t("autoscale.metrics.wait")}</dt>
          <dd>
            {t("autoscale.seconds", { count: Math.round(m.oldest_wait_s) })}
          </dd>
        </div>
        <div>
          <dt>{t("autoscale.metrics.runners")}</dt>
          <dd>
            {m.runners_online} ·{" "}
            {t("autoscale.metrics.slots", {
              busy: m.slots_busy,
              total: m.slots_total,
            })}
          </dd>
        </div>
        <div>
          <dt>{t("autoscale.metrics.decision")}</dt>
          <dd data-testid="autoscale-decision" data-action={d.action}>
            {t(`autoscale.action.${d.action}`, {
              from: d.current,
              to: d.desired,
            })}
            {" — "}
            {t(`autoscale.reason.${d.reason}`, { seconds: d.wait_s })}
          </dd>
        </div>
        <div>
          <dt>{t("autoscale.metrics.last")}</dt>
          <dd data-testid="autoscale-last">
            {status.last_outcome
              ? status.last_outcome.ok
                ? t("autoscale.outcome.ok", {
                    to: status.last_outcome.desired,
                    at: fmt(status.last_outcome.at),
                  })
                : t("autoscale.outcome.failed", {
                    error: status.last_outcome.error ?? "",
                    at: fmt(status.last_outcome.at),
                  })
              : "—"}
          </dd>
        </div>
      </dl>

      <SettingRow
        label={t("autoscale.mode.label")}
        hint={t(`autoscale.mode.hint.${draft.mode}`)}
        htmlFor="autoscale-mode"
      >
        <Select
          id="autoscale-mode"
          ariaLabel={t("autoscale.mode.label")}
          value={draft.mode}
          onValueChange={(value) => {
            setDraft({ ...draft, mode: value as AutoscaleMode });
          }}
          options={MODES.map((mode) => ({
            value: mode,
            label: t(`autoscale.mode.options.${mode}`),
          }))}
        />
      </SettingRow>
      {draft.mode === "webhook" && (
        <SettingRow
          label={t("autoscale.url.label")}
          hint={
            status.webhook_secret_set
              ? t("autoscale.url.hintSigned")
              : t("autoscale.url.hintUnsigned")
          }
          htmlFor="autoscale-url"
          layout="stacked"
        >
          <Input
            id="autoscale-url"
            type="url"
            value={draft.url}
            placeholder="https://orchestrator.example/scale"
            onChange={(event) => {
              setDraft({ ...draft, url: event.target.value });
            }}
            data-testid="autoscale-url"
          />
        </SettingRow>
      )}
      {FIELDS.map((field) => (
        <SettingRow
          key={field}
          label={t(`autoscale.fields.${field}.label`)}
          hint={t(`autoscale.fields.${field}.hint`)}
          htmlFor={`autoscale-${field}`}
        >
          <span className="ops-unit-field">
            <Input
              id={`autoscale-${field}`}
              type="number"
              min={0}
              step={field === "target_queue_per_slot" ? "0.1" : "1"}
              value={draft[field]}
              aria-label={t(`autoscale.fields.${field}.label`)}
              onChange={(event) => {
                setDraft({ ...draft, [field]: event.target.value });
              }}
              data-testid={`autoscale-${field}`}
            />
            <span className="ops-unit">
              {t(`autoscale.fields.${field}.unit`)}
            </span>
          </span>
        </SettingRow>
      ))}
    </Section>
  );
};

export const AutoscalePanel = () => {
  const { t } = useTranslation("adminRunners");
  const autoscale = useAutoscale();
  const save = useSaveAutoscale();
  const [failure, setFailure] = useState<Failure | null>(null);
  const state = autoscale.isPending
    ? "loading"
    : autoscale.isError
      ? "error"
      : "ready";
  return (
    <>
      <ViewState
        status={state}
        errorText={t("autoscale.loadFailed")}
        onRetry={() => void autoscale.refetch()}
        testId="autoscale-state"
      />
      {autoscale.data && (
        <AutoscaleView
          key={JSON.stringify(autoscale.data.policy)}
          status={autoscale.data}
          saving={save.isPending}
          failure={failure}
          onSave={(body) => {
            setFailure(null);
            save.mutate(body, {
              onError: (error) => setFailure({ code: failureCode(error) }),
            });
          }}
        />
      )}
    </>
  );
};
