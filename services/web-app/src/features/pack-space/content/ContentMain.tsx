import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState, ErrorState, Spinner } from "@shared/ui";
import { packErrorText } from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { ContentNavView } from "./ContentNav";
import { DocumentScreen } from "./DocumentScreen";
import { PartScreen } from "./PartScreen";
import { useContentData } from "./useContentData";
import { useContentRoute } from "./useContentRoute";
import "./space-content.css";

/** Слот `main.content`: плашка выпущенной версии и экран документа или раздела. */
const ContentMain = () => {
  const { t } = useTranslation("packSpace");
  const { versionRef, location } = useSpace();
  const data = useContentData();
  const route = useContentRoute(data);

  if (data.status === "loading") {
    return (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner size="lg" />
      </div>
    );
  }
  if (data.status === "error") {
    return (
      <ErrorState
        title={t("content.loadFailed")}
        description={packErrorText(data.error)}
        onRetry={data.refetch}
      />
    );
  }
  const currentName =
    route.kind === "document"
      ? (data.docs.find((doc) => doc.id === route.docId)?.name ?? route.docId)
      : route.kind === "part"
        ? t(`content.part.${route.part}`)
        : t("content.nav.documents");
  return (
    <div className="sp-ct" data-testid="ct-main">
      {/* Телефон: слева ничего, «что редактируем» сворачивается полосой в центре (4.5, до S11). */}
      <details className="sp-ct-phone-nav" key={location.search}>
        <summary>{t("content.nav.current", { name: currentName })}</summary>
        <ContentNavView data={data} route={route} testId="ct-phone" />
      </details>
      {data.readOnly && (
        <div className="sp-ct-banner" role="status" data-testid="ct-released">
          <Lock size="0.9375rem" aria-hidden="true" />
          <div>
            <b>
              {t("content.released.title", { version: versionRef.version })}
            </b>{" "}
            <span>{t("content.released.lead")}</span>
          </div>
        </div>
      )}
      {route.kind === "document" ? (
        <DocumentScreen
          data={data}
          docId={route.docId}
          segment={route.segment}
          file={route.file}
        />
      ) : route.kind === "part" ? (
        <PartScreen
          data={data}
          part={route.part}
          file={route.file}
          at={route.at}
        />
      ) : (
        <EmptyState
          framed
          title={t("content.noDocumentsTitle")}
          description={t("content.noDocumentsLead")}
          testId="ct-no-docs"
        />
      )}
    </div>
  );
};

export default ContentMain;
