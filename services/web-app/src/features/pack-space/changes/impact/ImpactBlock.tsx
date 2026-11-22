import { useCallback, useEffect, useMemo, useState } from "react";
import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PackVersionRef } from "@entities/pack-studio";
import { versionKey } from "@entities/pack-studio/outcome/impact";
import { VersionImpact, type VersionReport } from "./VersionImpact";
import "../../check/compare/outcome.css";
import "../../check/compare/rules.css";
import "../../check/compare/modes.css";
import "./impact.css";

/** Что блок сообщает диалогу: ждать ли расчёта, нужна ли отметка «я знаю», текст для тела PR. */
export type ImpactReport = {
  pending: boolean;
  needsAck: boolean;
  /** Компактная сводка для описания PR или MR; пусто, если результат не менялся. */
  summary: string;
};

export type ImpactBlockProps = {
  workspaceId: string;
  /** Версии с правками, не больше нескольких: на каждую свой расчёт. */
  versions: readonly PackVersionRef[];
  onReport: (report: ImpactReport) => void;
  /** Диалог закрывается перед переходом к правилу («Открыть правило»). */
  onLeave?: (() => void) | undefined;
  /** Адрес возврата из режима «Файлы»; по умолчанию экран «Результат» версии. */
  backTo?: string | undefined;
  onCreateScenario?: ((version: PackVersionRef) => void) | undefined;
};

/**
 * «Что изменится в результате» (template-studio-outcome.md, 3.7): сводка в стиле плана Terraform
 * по сценариям версий с правками. Не блокирует предложение изменений: только сообщает, нужна ли
 * осознанная отметка. Считает только смонтированный блок, то есть открытый диалог.
 */
export const ImpactBlock = ({
  workspaceId,
  versions,
  onReport,
  onLeave,
  backTo,
  onCreateScenario,
}: ImpactBlockProps) => {
  const { t } = useTranslation("packOutcome");
  const [reports, setReports] = useState<Record<string, VersionReport>>({});
  const keys = useMemo(() => versions.map(versionKey), [versions]);
  const onVersion = useCallback((key: string, report: VersionReport) => {
    setReports((prev) => {
      const old = prev[key];
      return old?.pending === report.pending &&
        old.needsAck === report.needsAck &&
        old.summary === report.summary
        ? prev
        : { ...prev, [key]: report };
    });
  }, []);

  useEffect(() => {
    const list = keys.map((key) => reports[key]);
    const known = list.filter((r): r is VersionReport => r !== undefined);
    onReport({
      // Версия, не успевшая отчитаться, считается ещё считающейся.
      pending: known.length < list.length || known.some((r) => r.pending),
      needsAck: known.some((r) => r.needsAck),
      summary: known
        .map((r) => r.summary)
        .filter((s) => s !== "")
        .join("\n\n"),
    });
  }, [keys, reports, onReport]);

  const warn = Object.values(reports).some((r) => r.needsAck);
  return (
    <section
      className="imp"
      aria-labelledby="impact-title"
      data-testid="impact-block"
    >
      <h3 id="impact-title" className="imp-title">
        {t("impact.title")}
      </h3>
      {versions.map((version) => (
        <VersionImpact
          key={versionKey(version)}
          workspaceId={workspaceId}
          version={version}
          titled={versions.length > 1}
          onReport={onVersion}
          onLeave={onLeave}
          backTo={backTo}
          onCreateScenario={onCreateScenario}
        />
      ))}
      {warn && (
        <p className="imp-warn" role="status" data-testid="impact-warning">
          <TriangleAlert size="1rem" aria-hidden="true" />
          <span>{t("impact.warning")}</span>
        </p>
      )}
    </section>
  );
};
