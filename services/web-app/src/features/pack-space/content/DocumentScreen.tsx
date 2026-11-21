import { Suspense, useEffect } from "react";
import { Lock } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { EmptyState, Spinner } from "@shared/ui";
import { writeUi } from "../context/memory";
import {
  DOC_SEGMENTS,
  type ContentDocument,
  type DocSegment,
} from "./contract";
import { SEGMENT_COMPONENTS } from "./registry";
import { MEMORY_DOC, MEMORY_SEGMENT } from "./useContentRoute";
import { useContentNav } from "./useContentNav";
import type { ContentData } from "./useContentData";

// Экран документа (pack-studio-ux.md, 5.5): название и три сегмента. Сам сегмент это файл
// расширения (`extend/segment-*.tsx`), здесь только рамка.

export const DocumentScreen = ({
  data,
  docId,
  segment,
  file,
}: {
  data: ContentData;
  docId: string;
  segment: DocSegment;
  file: string | null;
}) => {
  const { t } = useTranslation("packSpace");
  const nav = useContentNav();
  const doc: ContentDocument | undefined = data.docs.find(
    (item) => item.id === docId,
  );
  const Segment = SEGMENT_COMPONENTS[segment];
  const workspaceId = data.workspaceId;

  useEffect(() => {
    if (!doc) return;
    writeUi(workspaceId, MEMORY_DOC, doc.id);
    writeUi(workspaceId, MEMORY_SEGMENT, segment);
  }, [workspaceId, doc, segment]);

  if (!doc) {
    return (
      <EmptyState
        framed
        title={t("content.doc.notFoundTitle", { id: docId })}
        description={t("content.doc.notFoundLead")}
        testId="ct-doc-missing"
      />
    );
  }
  return (
    <div className="sp-ct-doc" data-testid="ct-doc" data-doc={doc.id}>
      <header className="sp-ct-head">
        <div className="sp-ct-title">
          <span className="sp-ct-kicker">{t("content.doc.kicker")}</span>
          <h1 className="sp-ct-h1">
            {doc.name}
            {data.readOnly && (
              <span className="sp-ct-badge" data-testid="ct-readonly">
                <Lock size="0.6875rem" aria-hidden="true" />
                {t("content.released.readOnly")}
              </span>
            )}
          </h1>
        </div>
        <nav className="sp-ct-seg" aria-label={t("content.doc.segments")}>
          {DOC_SEGMENTS.map((item) => (
            <Link
              key={item}
              replace
              to={nav.documentHref(doc.id, { segment: item })}
              className={clsx("sp-ct-seg-btn", item === segment && "on")}
              aria-current={item === segment ? "page" : undefined}
              data-testid={`ct-seg-${item}`}
              onClick={nav.guardClick}
            >
              {t(`content.doc.${item}`)}
            </Link>
          ))}
        </nav>
      </header>
      {Segment ? (
        <Suspense
          fallback={
            <div className="flex justify-center" style={{ padding: "2rem" }}>
              <Spinner size="md" />
            </div>
          }
        >
          <Segment
            // Другой документ или сегмент это другой экран: состояние форм и редакторов не переезжает.
            key={`${doc.id}:${segment}`}
            workspaceId={workspaceId}
            versionDir={data.versionDir}
            doc={doc}
            file={file}
            readOnly={data.readOnly}
          />
        </Suspense>
      ) : null}
    </div>
  );
};
