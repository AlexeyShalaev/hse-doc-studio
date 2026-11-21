import { useMemo } from "react";
import { FileX2, PenLine } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import {
  notifyPackFilesSaved,
  packErrorText,
  usePackSignatures,
} from "@entities/pack-studio";
import { Button, EmptyState, ErrorState, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useSpace } from "../../context/SpaceContext";
import { useSituation } from "../../context/useSituation";
import { useSpaceNav } from "../../context/useSpaceNav";
import type { DocumentSegmentProps } from "../contract";
import { useContentNav } from "../useContentNav";
import { PlacesEditor } from "./PlacesEditor";
import { useDocumentPdf } from "./useDocumentPdf";
import { slotsForDocument } from "./words";

// Сегмент «Подписи» экрана документа (pack-studio-ux.md, 5.5, срез S8c): места подписей по PDF
// документа, не уходя с экрана. Подписей у документа нет: короткая подсказка без сборки PDF.

const Wait = () => (
  <div className="flex justify-center" style={{ padding: "2rem" }}>
    <Spinner size="md" />
  </div>
);

const SignaturesView = ({
  workspaceId,
  doc,
  readOnly,
}: DocumentSegmentProps) => {
  const { t } = useTranslation("packSpace");
  const { versionRef } = useSpace();
  const space = useSpaceNav();
  const nav = useContentNav();
  const situation = useSituation();
  const slots = usePackSignatures(workspaceId, versionRef, null);
  // Решает наличие данных, а не статус запроса: после каждой правки список перечитывается, и
  // неудавшееся перечитывание не должно убирать редактор из-под рук.
  const loaded = slots.data;
  const mine = useMemo(
    () => (loaded ? slotsForDocument(loaded.slots, doc.id) : []),
    [loaded, doc.id],
  );
  const wanted = mine.length > 0;
  return (
    <div className="sp-ct-sgs" data-testid="ct-signatures" data-doc={doc.id}>
      {!loaded && slots.isPending && <Wait />}
      {!loaded && slots.isError && (
        <ErrorState
          compact
          description={packErrorText(slots.error)}
          onRetry={() => void slots.refetch()}
        />
      )}
      {loaded && mine.length === 0 && (
        <EmptyState
          framed
          icon={<PenLine size="1.5rem" />}
          title={t("content.signatures.emptyTitle")}
          description={t("content.signatures.emptyLead")}
          action={
            <Link
              className="btn sm"
              to={nav.partHref("signatures")}
              onClick={nav.guardClick}
            >
              {t("content.signatures.toOverview")}
            </Link>
          }
          testId="ct-sg-none"
        />
      )}
      {wanted && (
        <WithPdf
          workspaceId={workspaceId}
          docId={doc.id}
          docName={doc.name}
          inputs={situation.inputs}
          readOnly={readOnly}
          onCopy={() => {
            // Кнопку «Править копию» делает главная кнопка пространства (S4); параметр `copy`
            // зарезервирован за ним (12.6), как у «Текста».
            space.go({ extra: { copy: "1" } });
          }}
          onReset={situation.reset}
        />
      )}
    </div>
  );
};

const WithPdf = ({
  workspaceId,
  docId,
  docName,
  inputs,
  readOnly,
  onCopy,
  onReset,
}: {
  workspaceId: string;
  docId: string;
  docName: string;
  inputs: Record<string, string>;
  readOnly: boolean;
  onCopy: () => void;
  onReset: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const { versionRef } = useSpace();
  const pdf = useDocumentPdf(workspaceId, versionRef, docId, inputs);

  switch (pdf.state) {
    case "loading":
    case "building":
      return (
        <div
          className="sp-ct-sg-wait"
          role="status"
          data-testid="ct-sg-building"
        >
          <Spinner size="sm" />
          <span>{t("content.signatures.building")}</span>
          {pdf.state === "building" && (
            <Button size="xs" variant="ghost" onClick={pdf.cancel}>
              {t("content.signatures.cancel")}
            </Button>
          )}
        </div>
      );
    case "none":
      return (
        <EmptyState
          framed
          icon={<FileX2 size="1.5rem" />}
          title={t("content.signatures.noPdfTitle")}
          description={t("content.signatures.noPdf")}
          testId="ct-sg-nopdf"
        />
      );
    case "notInKit":
      return (
        <EmptyState
          framed
          icon={<FileX2 size="1.5rem" />}
          title={t("content.signatures.notInKitTitle")}
          description={t("content.signatures.notInKit")}
          action={
            <Button size="sm" variant="secondary" onClick={onReset}>
              {t("content.signatures.resetSituation")}
            </Button>
          }
          testId="ct-sg-notinkit"
        />
      );
    case "failed":
      return (
        <div data-testid="ct-sg-failed">
          <Notice
            tone="err"
            role="alert"
            text={
              <span>
                <b>{t("content.signatures.failed")}</b>{" "}
                {pdf.error !== null
                  ? packErrorText(pdf.error)
                  : (pdf.build?.error?.detail ?? "")}
              </span>
            }
            action={
              <Button size="xs" variant="secondary" onClick={pdf.retry}>
                {t("content.signatures.retry")}
              </Button>
            }
          />
        </div>
      );
    case "ready":
      return (
        <PlacesEditor
          workspaceId={workspaceId}
          versionRef={versionRef}
          buildId={pdf.build.id}
          pdfUrl={pdf.pdfUrl}
          documentName={docName}
          lang={pdf.lang}
          readOnly={readOnly}
          onCopy={onCopy}
          onSaved={() => {
            notifyPackFilesSaved(workspaceId);
          }}
        />
      );
  }
};

export default SignaturesView;
