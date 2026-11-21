import { ChevronLeft, Lock } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { EmptyState, ErrorState, Spinner } from "@shared/ui";
import { packErrorText } from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { useSpacePhone } from "../shell/phoneContext";
import { ContentNavView } from "./ContentNav";
import { DocumentScreen } from "./DocumentScreen";
import { PartScreen } from "./PartScreen";
import { contentListPatch } from "./link";
import { useContentData } from "./useContentData";
import { useContentNav } from "./useContentNav";
import { useContentRoute } from "./useContentRoute";
import "./space-content.css";

/** Слот `main.content`: плашка выпущенной версии и экран документа или раздела. */
const ContentMain = () => {
  const { t } = useTranslation("packSpace");
  const { versionRef } = useSpace();
  const phone = useSpacePhone();
  const nav = useSpaceNav();
  const contentNav = useContentNav();
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
  return (
    <div className="sp-ct" data-testid="ct-main">
      {/* Телефон (5.8): слева ничего. Список «Что редактируем» страница первого уровня, правка
          следующая страница с кнопкой «назад» к списку. */}
      {phone && route.kind !== "none" && (
        <Link
          to={nav.href(contentListPatch())}
          className="sp-ct-back"
          data-testid="ct-back"
          onClick={contentNav.guardClick}
        >
          <ChevronLeft size="1.125rem" aria-hidden="true" />
          {t("content.nav.label")}
        </Link>
      )}
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
      {phone && route.kind === "none" ? (
        <div className="sp-ct-list" data-testid="ct-list">
          <h1 className="sp-ct-h1">{t("content.nav.label")}</h1>
          <ContentNavView data={data} route={route} testId="ct-list" />
        </div>
      ) : route.kind === "document" ? (
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
