import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import type { PdfUploadStatus } from "../model/pdfUpload.model";
import type { AutoSyncInfo } from "../model/useAutoSync";

export type AutoSyncRowProps = {
  auto: AutoSyncInfo;
  /** Итог последней выгрузки PDF на сервер Студии; null, когда выгрузки у проекта нет. */
  pdf?: PdfUploadStatus | null;
  now: number;
};

/**
 * Строка автосинхронизации в панели: переключатель для проекта, что она делает
 * сейчас и итог последней выгрузки PDF. Только вид, данные приходят снаружи.
 */
export const AutoSyncRow = ({ auto, pdf = null, now }: AutoSyncRowProps) => {
  const { t } = useTranslation("gitSync");
  const stateText =
    auto.phase === "stopped" && auto.stop
      ? `${t("autoSync.state.stopped")}: ${t(`autoSync.stop.${auto.stop}`)}`
      : t(`autoSync.state.${auto.phase}`);

  return (
    <div
      className="flex flex-col"
      style={{ gap: 6 }}
      data-testid="auto-sync-row"
      data-phase={auto.phase}
    >
      <div className="flex items-center justify-between" style={{ gap: 12 }}>
        <div className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
          <strong id="auto-sync-label" style={{ fontSize: 12.5 }}>
            {t("autoSync.switch")}
          </strong>
          <span
            id="auto-sync-state"
            className="dim"
            style={{ fontSize: 11.5, lineHeight: 1.5 }}
            role="status"
          >
            {stateText}
          </span>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={auto.enabled}
          aria-labelledby="auto-sync-label"
          aria-describedby="auto-sync-state"
          className={clsx("toggle", auto.enabled && "on")}
          disabled={auto.isSaving}
          style={
            auto.isSaving ? { opacity: 0.5, cursor: "not-allowed" } : undefined
          }
          onClick={() => {
            auto.setEnabled(!auto.enabled);
          }}
        />
      </div>
      {pdf !== null && (
        <span
          className="dim"
          style={{ fontSize: 11.5, lineHeight: 1.5 }}
          data-testid="pdf-upload-line"
        >
          {pdf.last === null
            ? t("pdfUpload.none")
            : pdf.last.ok
              ? t("pdfUpload.ok", {
                  doc: pdf.last.docId,
                  when: formatPastTime(pdf.last.at, now),
                })
              : t("pdfUpload.failed", {
                  doc: pdf.last.docId,
                  reason: pdf.last.message ?? pdf.last.error ?? "",
                })}
        </span>
      )}
    </div>
  );
};
