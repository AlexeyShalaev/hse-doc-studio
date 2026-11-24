import { useEffect, useState } from "react";
import { Check, Circle, Clock, Loader2, Minus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Badge, Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { FleetBatch, FleetItem, FleetRunner } from "@entities/session";
import {
  useFleetBatch,
  useFleetCancel,
  useFleetDismiss,
  useFleetPlan,
  useFleetUpgrade,
  useRefreshRunners,
} from "../api/opsQueries";
import { defaultPicked, isManual, isSilent, summarize } from "../lib/fleet";

const STATE_ICON: Record<FleetItem["state"], React.ReactNode> = {
  pending: <Circle size="0.875rem" aria-hidden="true" />,
  waiting: <Clock size="0.875rem" aria-hidden="true" />,
  running: (
    <Loader2 size="0.875rem" className="animate-spin" aria-hidden="true" />
  ),
  succeeded: <Check size="0.875rem" aria-hidden="true" />,
  failed: <X size="0.875rem" aria-hidden="true" />,
  skipped: <Minus size="0.875rem" aria-hidden="true" />,
};

const Versions = ({ runner }: { runner: FleetRunner }) => {
  const { t } = useTranslation("adminRunnerInstall");
  return (
    <span className="form-hint">
      {t("fleet.versions", {
        from: runner.version,
        to: runner.target_version,
      })}
    </span>
  );
};

/** Строка выбора: чем обновляется раннер, что с ним сейчас и, если отсюда нельзя, что сделать руками. */
const PickRow = ({
  runner,
  checked,
  onToggle,
}: {
  runner: FleetRunner;
  checked: boolean;
  onToggle: () => void;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  const manual = isManual(runner);
  return (
    <li
      className="flex items-center"
      style={{ gap: "0.625rem", flexWrap: "wrap", fontSize: "0.8125rem" }}
      data-testid={`fleet-row-${runner.runner_id}`}
      data-kind={runner.kind}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={manual}
        onChange={onToggle}
        aria-label={runner.name}
        data-testid={`fleet-check-${runner.runner_id}`}
      />
      <span style={{ flex: 1, minWidth: "10rem", wordBreak: "break-all" }}>
        <span style={{ fontWeight: 600 }}>{runner.name}</span>{" "}
        <Versions runner={runner} />
        {manual && runner.manual_reason !== null && (
          <span
            className="form-hint"
            style={{ display: "block" }}
            data-testid={`fleet-manual-${runner.runner_id}`}
          >
            {t(`fleet.manual.${runner.manual_reason}`)}
          </span>
        )}
        {!manual && runner.running_jobs > 0 && (
          <span
            className="form-hint"
            style={{ display: "block" }}
            data-testid={`fleet-load-${runner.runner_id}`}
          >
            {t("fleet.busyNote", { count: runner.running_jobs })}
          </span>
        )}
        {!manual && isSilent(runner) && (
          <span
            className="form-hint"
            style={{ display: "block" }}
            data-testid={`fleet-silent-${runner.runner_id}`}
          >
            {t("fleet.silentNote")}
          </span>
        )}
      </span>
      <Badge variant={manual ? "warning" : "default"}>
        {manual ? t("fleet.manualBadge") : t(`fleet.kind.${runner.kind}`)}
      </Badge>
    </li>
  );
};

const Selection = ({
  items,
  picked,
  onChange,
}: {
  items: readonly FleetRunner[];
  picked: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
}) => (
  <ul
    className="flex flex-col"
    style={{ gap: "0.625rem", margin: 0, padding: 0, listStyle: "none" }}
    data-testid="fleet-list"
  >
    {items.map((runner) => (
      <PickRow
        key={runner.runner_id}
        runner={runner}
        checked={picked.has(runner.runner_id)}
        onToggle={() => {
          const next = new Set(picked);
          if (!next.delete(runner.runner_id)) next.add(runner.runner_id);
          onChange(next);
        }}
      />
    ))}
  </ul>
);

/** Причина, по которой раннер не обновлён или пропущен: свой текст, иначе текст установки раннера. */
const useReason = () => {
  const { t } = useTranslation("adminRunnerInstall");
  return (item: FleetItem): string => {
    const code = item.code ?? "unknown";
    const reason = t([
      `fleet.reason.${code}`,
      `error.${code}`,
      "fleet.reason.unknown",
    ]);
    if (item.rolled_back === true) return `${reason} ${t("fleet.rolledBack")}`;
    if (item.rolled_back === false)
      return `${reason} ${t("fleet.rollbackFailed")}`;
    return reason;
  };
};

const ProgressRow = ({ item }: { item: FleetItem }) => {
  const { t } = useTranslation("adminRunnerInstall");
  const reason = useReason();
  const failed = item.state === "failed" || item.state === "skipped";
  return (
    <li
      className="flex items-center"
      style={{ gap: "0.625rem", fontSize: "0.8125rem" }}
      data-testid={`fleet-item-${item.runner_id}`}
      data-state={item.state}
    >
      <span aria-hidden="true" style={{ display: "inline-flex" }}>
        {STATE_ICON[item.state]}
      </span>
      <span style={{ flex: 1, minWidth: 0, wordBreak: "break-all" }}>
        <span style={{ fontWeight: 600 }}>{item.name}</span>{" "}
        <span className="form-hint">
          {item.state === "succeeded"
            ? t("fleet.item.succeeded", {
                version: item.to_version || item.from_version,
              })
            : t(`fleet.item.${item.state}`)}
        </span>
        {failed && (
          <span
            className="form-hint"
            style={{ display: "block" }}
            data-testid={`fleet-reason-${item.runner_id}`}
          >
            {reason(item)}
            {item.detail ? ` (${item.detail})` : ""}
          </span>
        )}
      </span>
    </li>
  );
};

const Progress = ({ batch }: { batch: FleetBatch }) => {
  const { t } = useTranslation("adminRunnerInstall");
  const sum = summarize(batch.items);
  return (
    <>
      <p style={{ margin: 0 }} data-testid="fleet-summary">
        {batch.state === "running"
          ? t("fleet.running", {
              done: sum.total - sum.active,
              total: sum.total,
            })
          : t("fleet.summary", {
              done: sum.done,
              skipped: sum.skipped,
              failed: sum.failed,
            })}
      </p>
      <ol
        className="flex flex-col"
        style={{ gap: "0.5rem", margin: 0, padding: 0, listStyle: "none" }}
        data-testid="fleet-progress"
      >
        {batch.items.map((item) => (
          <ProgressRow key={item.runner_id} item={item} />
        ))}
      </ol>
    </>
  );
};

/**
 * «Обновить все раннеры»: устаревшие раннеры с видом, текущей и новой версией, выбор и один запуск. Ход и итог видны
 * тут же. Закрытие вне идущего запуска значит отказ от предложения для этой версии Студии (для всех админов).
 */
export const FleetUpgradeDialog = ({ onClose }: { onClose: () => void }) => {
  const { t } = useTranslation("adminRunnerInstall");
  const plan = useFleetPlan();
  const start = useFleetUpgrade();
  const cancel = useFleetCancel();
  const dismiss = useFleetDismiss();
  const refresh = useRefreshRunners();
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const [started, setStarted] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const batchId = started ?? plan.data?.batch?.id ?? null;
  const batch = useFleetBatch(batchId).data ?? null;
  const live = batch?.state === "running" ? batch : null;
  const state = batch?.state;

  // Версии и состояния раннеров в таблице меняются по ходу запуска и после него.
  useEffect(() => {
    if (state === "finished") refresh();
  }, [state, refresh]);

  const items = plan.data?.items ?? [];
  const chosen = picked ?? defaultPicked(items);
  const upgradable = items.filter((item) => !isManual(item));
  const all = chosen.size === upgradable.length;

  const close = () => {
    if (live === null && plan.data) dismiss.mutate(plan.data.server_version);
    onClose();
  };
  const run = () => {
    setFailure(null);
    start.mutate([...chosen], {
      onSuccess: (created) => {
        setStarted(created.id);
      },
      onError: (error) => {
        setFailure(failureCode(error));
      },
    });
  };

  const version = plan.data?.server_version ?? "";
  const failureText =
    failure === "fleet_busy"
      ? t("fleet.busy")
      : failure === "input_invalid"
        ? t("fleet.invalid")
        : t("fleet.startFailed");

  return (
    <Modal
      isOpen
      onClose={close}
      title={t("fleet.title", { version })}
      description={t("fleet.lead", { version })}
      width={640}
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem", fontSize: "0.8125rem" }}
        data-testid="fleet-dialog"
      >
        {plan.isPending && <Spinner size="sm" />}
        {plan.isError && (
          <Notice tone="err" role="alert" text={t("fleet.loadFailed")} />
        )}
        {batch !== null ? (
          <Progress batch={batch} />
        ) : (
          plan.data && (
            <>
              {upgradable.length === 0 ? (
                <p style={{ margin: 0 }} data-testid="fleet-none">
                  {t("fleet.none")}
                </p>
              ) : (
                <p style={{ margin: 0 }} data-testid="fleet-found">
                  {t("fleet.found", { count: items.length })}
                </p>
              )}
              <Selection items={items} picked={chosen} onChange={setPicked} />
              {upgradable.length > 0 && (
                <>
                  <p style={{ margin: 0 }}>{t("fleet.how")}</p>
                  <p style={{ margin: 0 }}>{t("fleet.restart")}</p>
                </>
              )}
            </>
          )
        )}
        {failure && (
          <div data-testid="fleet-start-failure">
            <Notice tone="err" role="alert" text={failureText} />
          </div>
        )}
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", justifyContent: "flex-end" }}
        >
          {batch === null && upgradable.length > 0 && (
            <>
              <Button
                type="button"
                variant="ghost"
                onClick={close}
                data-testid="fleet-dismiss"
              >
                {t("fleet.notNow")}
              </Button>
              <Button
                type="button"
                variant="primary"
                disabled={chosen.size === 0 || start.isPending}
                onClick={run}
                data-testid="fleet-start"
              >
                {all
                  ? t("fleet.startAll")
                  : t("fleet.startSelected", { count: chosen.size })}
              </Button>
            </>
          )}
          {batch === null && plan.data && upgradable.length === 0 && (
            <Button
              type="button"
              variant="ghost"
              onClick={close}
              data-testid="fleet-close"
            >
              {t("fleet.close")}
            </Button>
          )}
          {live !== null && (
            <>
              <Button
                type="button"
                variant="ghost"
                disabled={cancel.isPending || live.cancel_requested}
                onClick={() => {
                  cancel.mutate(live.id);
                }}
                data-testid="fleet-cancel"
              >
                {live.cancel_requested
                  ? t("fleet.cancelRequested")
                  : t("fleet.cancelRun")}
              </Button>
              <Button
                type="button"
                variant="primary"
                onClick={close}
                data-testid="fleet-hide"
              >
                {t("fleet.hide")}
              </Button>
            </>
          )}
          {state === "finished" && (
            <Button
              type="button"
              variant="primary"
              onClick={close}
              data-testid="fleet-close"
            >
              {t("fleet.close")}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
};
