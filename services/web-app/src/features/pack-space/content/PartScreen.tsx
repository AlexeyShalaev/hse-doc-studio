import { Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui";
import type { ContentPart } from "./contract";
import { PART_COMPONENTS } from "./registry";
import type { ContentData } from "./useContentData";

// Раздел версии: заголовок и файл расширения (`extend/part-*.tsx`).
export const PartScreen = ({
  data,
  part,
  file,
  at,
}: {
  data: ContentData;
  part: ContentPart;
  file: string | null;
  at: string | null;
}) => {
  const { t } = useTranslation("packSpace");
  const Part = PART_COMPONENTS[part];
  return (
    <div className="sp-ct-doc" data-testid="ct-part" data-part={part}>
      <header className="sp-ct-head">
        <div className="sp-ct-title">
          <h1 className="sp-ct-h1">{t(`content.part.${part}`)}</h1>
        </div>
      </header>
      {Part ? (
        <Suspense
          fallback={
            <div className="flex justify-center" style={{ padding: "2rem" }}>
              <Spinner size="md" />
            </div>
          }
        >
          <Part
            key={part}
            workspaceId={data.workspaceId}
            versionDir={data.versionDir}
            part={part}
            at={at}
            file={file}
            readOnly={data.readOnly}
          />
        </Suspense>
      ) : null}
    </div>
  );
};
