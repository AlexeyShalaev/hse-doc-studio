import { lazy, Suspense, useCallback } from "react";
import { pickLocalized } from "@shared/lib";
import { Spinner } from "@shared/ui";
import { useTranslation } from "react-i18next";
import { useModelEditor } from "../../model/modelEditor";
import type { VersionSectionProps } from "../VersionForm";

// Форма точек сдачи и порядка подписания (срез T13): свой чанк, грузится с разделом.
const PackSubmissionForm = lazy(() =>
  import("@features/pack-submission-form").then((m) => ({
    default: m.PackSubmissionForm,
  })),
);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * Раздел «Сдача и подписи» формы версии (5.5-5.8): профили сдачи, пункты, `extra_items`,
 * порядок маршрута, `signing_slots` и «Маршрут в этой комбинации». Правки идут своим
 * маршрутом `.../submission` (строгий разбор лоадера по профилю) в той же очереди, что
 * правки модели, и обновляют модель; названия документов берутся из модели версии.
 */
export const SubmissionSection = ({
  workspaceId,
  path,
  onSaved,
}: VersionSectionProps) => {
  const { i18n } = useTranslation();
  const { model } = useModelEditor();
  const docName = useCallback(
    (doc: string): string | null => {
      const found = model.documents.find((d) => d.id === doc);
      const name = isRecord(found?.data) ? found.data.name : undefined;
      if (isRecord(name)) {
        const strings = Object.fromEntries(
          Object.entries(name).filter(
            (entry): entry is [string, string] => typeof entry[1] === "string",
          ),
        );
        return pickLocalized(strings, i18n.language, doc);
      }
      return typeof name === "string" ? name : null;
    },
    [model.documents, i18n.language],
  );
  const saved = useCallback(
    (changed: string) => {
      onSaved([changed]);
    },
    [onSaved],
  );
  return (
    <Suspense
      fallback={
        <div className="pf-loading">
          <Spinner size="md" />
        </div>
      }
    >
      <PackSubmissionForm
        workspaceId={workspaceId}
        path={path}
        revision={model.manifest.etag}
        docName={docName}
        onSaved={saved}
      />
    </Suspense>
  );
};
