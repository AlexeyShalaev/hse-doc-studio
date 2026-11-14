import { useState } from "react";
import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import {
  DISK_AUTO_PERCENT_MAX,
  DISK_AUTO_PERCENT_MIN,
  type RunnerDiskAuto,
  type RunnerDiskAutoLast,
  type RunnerDiskAutoRequest,
} from "../model/runnerDisk.schema";
import { DiskBlock } from "./RunnerDiskBlocks";
import { diskSize, diskWhen } from "./format";

// Блок «Автоочистка» в «Диске» общего раннера (docs/design/storage-cleanup.md, 14.6): переключатель,
// порог в процентах свободного места и строка о последнем запуске. Только в админке.

const percentOf = (last: RunnerDiskAutoLast): number =>
  last.total_bytes > 0
    ? Math.round((last.free_bytes * 100) / last.total_bytes)
    : 0;

/** Строка «Автоочистка: последний раз …» по итогу последнего запуска. */
const useAutoLastText = () => {
  const { t } = useTranslation("runnerDisk");
  return (last: RunnerDiskAutoLast | null): string => {
    if (last === null) return t("auto.lastNever");
    const size = diskSize(last.freed_bytes);
    if (last.finished_at === null) {
      return t("auto.lastRunning", { when: diskWhen(last.started_at) });
    }
    const when = diskWhen(last.finished_at);
    if (last.state === "lost") return t("auto.lastLost", { when });
    if (last.state === "error") return t("auto.lastError", { when, size });
    if (last.state === "cancelled")
      return t("auto.lastCancelled", { when, size });
    return t("auto.lastDone", { when, size });
  };
};

export type RunnerDiskAutoBlockProps = {
  auto: RunnerDiskAuto;
  /** Сохранить настройку; без него блок только показывает. */
  onSave?: ((request: RunnerDiskAutoRequest) => void) | undefined;
  pending?: boolean | undefined;
};

export const RunnerDiskAutoBlock = ({
  auto,
  onSave,
  pending = false,
}: RunnerDiskAutoBlockProps) => {
  const { t } = useTranslation("runnerDisk");
  const lastText = useAutoLastText();
  const [enabled, setEnabled] = useState(auto.enabled);
  const [percent, setPercent] = useState(String(auto.min_free_percent));

  const value = Number(percent);
  const valid =
    Number.isInteger(value) &&
    value >= DISK_AUTO_PERCENT_MIN &&
    value <= DISK_AUTO_PERCENT_MAX;
  const dirty =
    enabled !== auto.enabled || (valid && value !== auto.min_free_percent);
  // Настройку раннера без Docker-части менять незачем: там автоочистка не нужна вовсе.
  const editable =
    onSave !== undefined && (auto.supported || auto.reason === "outdated");
  const last = auto.last;

  return (
    <DiskBlock
      testId="runner-disk-auto"
      icon={<Sparkles size="0.875rem" aria-hidden="true" />}
      title={t("auto.title")}
      hint={
        auto.supported
          ? t("auto.hint", { minutes: auto.interval_min })
          : t(`auto.reason.${auto.reason ?? "outdated"}`, {
              version: auto.min_version,
            })
      }
    >
      {editable && (
        <div
          className="flex flex-wrap items-end"
          style={{ gap: "0.5rem 1rem" }}
        >
          <label
            className="flex items-center"
            style={{ gap: "0.5rem", fontSize: "0.75rem" }}
          >
            <Switch
              checked={enabled}
              onChange={setEnabled}
              disabled={pending}
              testId="runner-disk-auto-enabled"
            />
            {t("auto.switch")}
          </label>
          <label
            className="flex items-center"
            style={{ gap: "0.375rem", fontSize: "0.75rem" }}
          >
            <span className="dim">{t("auto.threshold")}</span>
            <input
              className="input mono"
              type="number"
              inputMode="numeric"
              min={DISK_AUTO_PERCENT_MIN}
              max={DISK_AUTO_PERCENT_MAX}
              step={1}
              value={percent}
              disabled={pending || !enabled}
              aria-invalid={!valid}
              onChange={(event) => {
                setPercent(event.target.value);
              }}
              style={{ width: "4.5rem" }}
              data-testid="runner-disk-auto-percent"
            />
            <span className="dim">%</span>
          </label>
          <Button
            type="button"
            size="xs"
            variant="secondary"
            disabled={!dirty || !valid || pending}
            onClick={() => {
              onSave({ enabled, min_free_percent: value });
            }}
            data-testid="runner-disk-auto-save"
          >
            {t("auto.save")}
          </Button>
        </div>
      )}
      {editable && !valid && (
        <span
          role="alert"
          className="text-xs text-c-err"
          data-testid="runner-disk-auto-invalid"
        >
          {t("auto.invalid", {
            min: DISK_AUTO_PERCENT_MIN,
            max: DISK_AUTO_PERCENT_MAX,
          })}
        </span>
      )}
      {(auto.supported || last !== null) && (
        <span
          className="dim"
          style={{ fontSize: "0.71875rem" }}
          data-testid="runner-disk-auto-last"
        >
          {lastText(last)}
          {last !== null &&
            ` (${t("auto.freeAt", { percent: percentOf(last) })})`}
        </span>
      )}
    </DiskBlock>
  );
};
