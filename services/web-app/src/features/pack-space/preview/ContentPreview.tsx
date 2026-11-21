import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import { EmptyState, ErrorState, Spinner } from "@shared/ui";
import { resolveDocumentFile } from "../content/documents";
import { requestRevealLine } from "../content/text/revealLine";
import { useContentData } from "../content/useContentData";
import { useContentNav } from "../content/useContentNav";
import { useContentRoute } from "../content/useContentRoute";
import PreviewPanel from "./PreviewPanel";

/**
 * Слот `details.content`: предпросмотр PDF документа, открытого слева (pack-studio-ux.md, 5.5).
 * У разделов формы и у «Все файлы» страницы нет: пояснение вместо панели. Под страницей замечания к
 * файлу, который открыт в «Тексте» (по умолчанию основной файл документа).
 */
const ContentPreview = () => {
  const { t, i18n } = useTranslation("packSpace");
  const data = useContentData();
  const route = useContentRoute(data);
  const nav = useContentNav();

  if (data.status === "loading") {
    return (
      <div className="flex justify-center" style={{ padding: "1.5rem" }}>
        <Spinner size="md" />
      </div>
    );
  }
  if (data.status === "error") {
    return (
      <ErrorState
        compact
        description={packErrorText(data.error)}
        onRetry={data.refetch}
      />
    );
  }
  const doc =
    route.kind === "document"
      ? data.docs.find((item) => item.id === route.docId)
      : undefined;
  if (route.kind !== "document" || !doc) {
    return (
      <div className="sp-pv" data-testid="sp-pv-none">
        <EmptyState
          compact
          icon={<FileText size="1.25rem" />}
          title={t("preview.noDocument.title")}
          description={t("preview.noDocument.lead")}
        />
      </div>
    );
  }
  const file = resolveDocumentFile(
    doc,
    route.file,
    i18n.language,
    data.versionDir,
  );
  return (
    <PreviewPanel
      // Другой документ это другая страница: сборка, выбор варианта и списки не переезжают.
      key={doc.id}
      docId={doc.id}
      docName={doc.name}
      file={file?.path ?? null}
      onLine={(line) => {
        if (!file) return;
        requestRevealLine(file.path, line);
        // Строка видна только в «Тексте»: из «Условий» и «Подписей» переходим туда.
        if (route.segment !== "text") {
          nav.toDocument(doc.id, { segment: "text", file: file.path });
        }
      }}
    />
  );
};

export default ContentPreview;
