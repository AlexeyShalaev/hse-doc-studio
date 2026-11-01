import { useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { FileDropZone, type FileDropZoneHandle } from "@shared/ui/FileDropZone";
import { Notice } from "@shared/ui/ConflictKit";
import { ProgressBar } from "@shared/ui/ProgressBar";
import type { ProjectImportResult } from "@entities/session";
import type { ImportFailure, ImportStage } from "../model/useProjectImport";
import { ImportFileCard } from "./ImportFileCard";
import { ImportResultView } from "./ImportResultView";
import { useFailureText } from "./useFailureText";

export type ProjectImportViewProps = {
  stage: ImportStage;
  /** Выбранный файл: имя и размер (сам File нужен только окну). */
  file: { name: string; size: number } | null;
  percent: number;
  result: ProjectImportResult | null;
  failure: ImportFailure | null;
  onPick: (file: File | null) => void;
};

const isZip = (file: File): boolean => file.name.toLowerCase().endsWith(".zip");

// Тело окна импорта по шагам: выбор файла, загрузка и проверка, итог, отказ.
export const ProjectImportView = ({
  stage,
  file,
  percent,
  result,
  failure,
  onPick,
}: ProjectImportViewProps) => {
  const { t } = useTranslation("projectImport");
  const failureText = useFailureText();
  const zoneRef = useRef<FileDropZoneHandle>(null);
  const [wrongKind, setWrongKind] = useState(false);

  if (stage === "done" && result) return <ImportResultView result={result} />;

  if (stage === "uploading") {
    const unpacking = percent >= 100;
    return (
      <div className="flex flex-col" style={{ gap: 14 }}>
        {file && (
          <ImportFileCard name={file.name} size={file.size} editable={false} />
        )}
        <div className="flex flex-col" style={{ gap: 8 }}>
          <p
            className="dim"
            style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}
          >
            {t("uploading.lead")}
          </p>
          <ProgressBar
            percent={unpacking ? null : percent}
            label={unpacking ? t("uploading.unpacking") : t("uploading.label")}
          />
          <div
            className="dim flex items-center"
            style={{ gap: 6, fontSize: 11.5 }}
            role="status"
          >
            {unpacking ? (
              <>
                <Loader2 size={12} className="spin" aria-hidden="true" />
                {t("uploading.unpacking")}
              </>
            ) : (
              t("uploading.percent", { percent: Math.round(percent) })
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ gap: 14 }}>
      <FileDropZone
        ref={zoneRef}
        showZone={file === null}
        accept=".zip,application/zip"
        isAcceptable={isZip}
        onFile={(picked) => {
          setWrongKind(false);
          onPick(picked);
        }}
        onReject={() => {
          setWrongKind(true);
        }}
        title={t("drop")}
        action={t("choose")}
        activeTitle={t("dropActive")}
        hint={t("accept")}
        inputLabel={t("inputLabel")}
        testId="project-import-dropzone"
        inputTestId="project-import-input"
      />
      {file && (
        <ImportFileCard
          name={file.name}
          size={file.size}
          editable
          onReplace={() => {
            zoneRef.current?.open();
          }}
          onRemove={() => {
            onPick(null);
          }}
        />
      )}
      {wrongKind && <Notice tone="err" role="alert" text={t("wrongKind")} />}
      {failure && (
        <Notice
          tone="err"
          role="alert"
          text={
            <>
              <strong style={{ fontWeight: 600 }}>{t("failure.title")}</strong>
              <span style={{ display: "block" }}>{failureText(failure)}</span>
            </>
          }
        />
      )}
      {!file && !failure && (
        <p
          className="dim"
          style={{ margin: 0, fontSize: 12, lineHeight: 1.55 }}
        >
          {t("explain")}
        </p>
      )}
    </div>
  );
};
