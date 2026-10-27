import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui/Spinner";
import { DiffPatch, countChanges } from "@shared/ui/DiffPatch";
import {
  type ConflictResolution,
  type TemplateDiffView,
  useTemplateFileDiff,
} from "@entities/template-update";

export type TemplateFileDiffProps = {
  projectId: string;
  path: string;
  view: TemplateDiffView;
  toVersion?: string;
  resolution?: ConflictResolution;
  maxHeight?: number;
};

/** Дифф одного файла относительно шаблона в той же вёрстке, что и «Версии». */
export const TemplateFileDiff = ({
  projectId,
  path,
  view,
  toVersion,
  resolution,
  maxHeight = 360,
}: TemplateFileDiffProps) => {
  const { t } = useTranslation("templateUpdate");
  const { data, isLoading, isError } = useTemplateFileDiff(projectId, {
    path,
    view,
    ...(toVersion ? { toVersion } : {}),
    ...(resolution ? { resolution } : {}),
  });
  const stat = useMemo(
    () =>
      data && !data.binary ? countChanges(data.patch) : { add: 0, del: 0 },
    [data],
  );

  if (isLoading) {
    return (
      <div className="flex justify-center" style={{ padding: 16 }}>
        <Spinner size="sm" />
      </div>
    );
  }
  if (isError || !data) return null;
  if (data.binary) {
    return (
      <div className="dim" style={{ padding: 12, fontSize: 11.5 }}>
        {t("dialog.binary")}
      </div>
    );
  }
  return (
    <DiffPatch
      file={{ path: data.path, change: "M", patch: data.patch, binary: false }}
      stat={stat}
      maxHeight={maxHeight}
    />
  );
};
