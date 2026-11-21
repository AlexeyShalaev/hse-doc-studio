import { PenLine } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { packErrorText, usePackSignatures } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib";
import { EmptyState, ErrorState, Spinner } from "@shared/ui";
import { useSpace } from "../../context/SpaceContext";
import type { ContentPartProps } from "../contract";
import { useContentData } from "../useContentData";
import { useContentNav } from "../useContentNav";
import { entryKind, entryPage, documentPlacesOf } from "./words";
import "./space-content-signatures.css";

// Раздел «Подписи и места» (pack-studio-ux.md, 4.1 и 5.5, срез S8c): какие подписи бывают в
// документах версии и где они стоят. Расставлять рамки по странице идут в документ, во вкладку
// «Подписи»: отсюда туда по ссылке «Расставить». Порядок подписания живёт в «Сроках и сдаче».

const SignaturesOverview = ({ workspaceId }: ContentPartProps) => {
  const { t, i18n } = useTranslation("packSpace");
  const { versionRef } = useSpace();
  const nav = useContentNav();
  const { docs } = useContentData();
  const query = usePackSignatures(workspaceId, versionRef, null);

  if (!query.data && query.isPending) {
    return (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner size="md" />
      </div>
    );
  }
  if (!query.data) {
    return (
      <ErrorState
        compact
        description={packErrorText(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const slots = query.data.slots;
  const nameOf = (docId: string): string =>
    docs.find((doc) => doc.id === docId)?.name ?? docId;
  const known = new Set(docs.map((doc) => doc.id));

  return (
    <div className="sp-ct-sgo" data-testid="ct-sg-overview">
      <p className="sp-ct-sg-lead">{t("content.signatures.overview.lead")}</p>
      {slots.length === 0 ? (
        <EmptyState
          framed
          icon={<PenLine size="1.5rem" />}
          title={t("content.signatures.overview.emptyTitle")}
          description={t("content.signatures.overview.emptyLead")}
          testId="ct-sgo-empty"
        />
      ) : (
        <ul className="sp-ct-sg-list">
          {slots.map((slot) => {
            const label = pickLocalized(slot.label, i18n.language, slot.id);
            return (
              <li
                key={slot.id}
                className="sp-ct-sg-card"
                data-testid={`ct-sgo-${slot.id}`}
              >
                <div className="sp-ct-sg-head">
                  <b className="sp-ct-sg-name">{label}</b>
                  {slot.required && (
                    <span className="sp-ct-sg-chip">
                      {t("content.signatures.required")}
                    </span>
                  )}
                  {slot.per_author && (
                    <span className="sp-ct-sg-chip">
                      {t("content.signatures.perAuthor")}
                    </span>
                  )}
                </div>
                <p className="sp-ct-sg-note">
                  {entryKind(slot.default_place) === "page"
                    ? t("content.signatures.overview.commonPage", {
                        page: entryPage(slot.default_place),
                      })
                    : t("content.signatures.overview.commonText")}
                </p>
                {slot.applies_to.length === 0 ? (
                  <p className="sp-ct-sg-note warn">
                    {t("content.signatures.overview.noDocs")}
                  </p>
                ) : (
                  <ul className="sp-ct-sgo-docs">
                    {documentPlacesOf(slot).map(({ docId, status }) => (
                      <li key={docId} data-status={status}>
                        <span className="sp-ct-sgo-doc">{nameOf(docId)}</span>
                        <span className="sp-ct-sg-note">
                          {t(`content.signatures.overview.${status}`)}
                        </span>
                        {known.has(docId) && (
                          <Link
                            className="sp-ct-sgo-go"
                            to={nav.documentHref(docId, {
                              segment: "signatures",
                            })}
                            onClick={nav.guardClick}
                            data-testid={`ct-sgo-go-${slot.id}-${docId}`}
                          >
                            {t("content.signatures.overview.place")}
                          </Link>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className="sp-ct-sg-note">
        {t("content.signatures.overview.order")}{" "}
        <Link
          to={nav.partHref("deadlines")}
          onClick={nav.guardClick}
          data-testid="ct-sgo-order"
        >
          {t("content.signatures.overview.orderLink")}
        </Link>
      </p>
    </div>
  );
};

export default SignaturesOverview;
