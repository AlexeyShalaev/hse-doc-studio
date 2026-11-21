import { useMemo, useState } from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackSignatures,
  usePatchPackSignatures,
  type PackPlaceOp,
  type PackSignatureSlot,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  dateMoveOpFrom,
  placeOpFrom,
  stamperStateOf,
} from "@features/pack-places";
import {
  PdfStampEditor,
  type DateMarkPlace,
} from "@features/signature-stamper";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import { Button, ErrorState, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { PlaceCard } from "./PlaceCard";
import "./space-content-signatures.css";

// Редактор мест подписей по месту (pack-studio-ux.md, 5.5, срез S8c): готовая страница документа,
// на ней рамки подписей, справа или ниже карточки со словами. Каждая правка сразу пишется в описание
// версии точечной правкой (модель и жесты те же, что у прежнего редактора, `features/pack-places`);
// выпущенная версия только для просмотра.

export type PlacesEditorProps = {
  workspaceId: string;
  versionRef: PackVersionRef;
  /** Удачная сборка PDF документа: по ней сервер считает рамки. */
  buildId: string;
  pdfUrl: string;
  /** Название документа: подпись над страницей. */
  documentName: string;
  /** Язык документа: месяц в примере даты. */
  lang: string;
  /** Выпущенная версия или отказ сервера писать. */
  readOnly: boolean;
  /** «Править копию»; в режиме чтения рядом с пометкой. */
  onCopy: () => void;
  /** Места записаны в описание версии (`path`). */
  onSaved?: (path: string) => void;
};

export const PlacesEditor = ({
  workspaceId,
  versionRef,
  buildId,
  pdfUrl,
  documentName,
  lang,
  readOnly: readOnlyProp,
  onCopy,
  onSaved,
}: PlacesEditorProps) => {
  const { t, i18n } = useTranslation("packSpace");
  const query = usePackSignatures(workspaceId, versionRef, buildId);
  const patch = usePatchPackSignatures(workspaceId, versionRef, buildId);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [stale, setStale] = useState(false);
  const data = query.data;
  const sharedSuffix = t("content.signatures.sharedSuffix");
  const stamper = useMemo(
    () =>
      data
        ? stamperStateOf(data, (slot) =>
            slot.document?.kind === "default"
              ? Object.fromEntries(
                  Object.entries(slot.label).map(([lng, text]) => [
                    lng,
                    `${text} (${sharedSuffix})`,
                  ]),
                )
              : slot.label,
          )
        : null,
    [data, sharedSuffix],
  );

  if (query.isPending) {
    return (
      <div className="flex justify-center" style={{ padding: "1.5rem" }}>
        <Spinner size="md" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <ErrorState
        compact
        description={packErrorText(query.error)}
        onRetry={() => void query.refetch()}
        testId="ct-sg-error"
      />
    );
  }
  if (!stamper) return null;

  const loaded = query.data;
  const readOnly = readOnlyProp || loaded.read_only !== null;
  const slotOf = (id: string): PackSignatureSlot | undefined =>
    loaded.slots.find((slot) => slot.id === id);

  const send = (op: PackPlaceOp | null) => {
    if (op === null || readOnly) return;
    setStale(false);
    patch.mutate(
      { body: { build_id: buildId, ops: [op] }, etag: loaded.etag },
      {
        onSuccess: (next) => {
          onSaved?.(next.path);
        },
        onError: (error) => {
          if (error instanceof ApiError && error.code === "stale_file") {
            setStale(true);
            void query.refetch();
          }
        },
      },
    );
  };

  const error = patch.error;
  const staleError = error instanceof ApiError && error.code === "stale_file";
  const reason =
    error instanceof ApiError && typeof error.data?.reason === "string"
      ? error.data.reason
      : null;
  const applicable = loaded.slots.filter((slot) => slot.document !== null);
  const others = loaded.slots.filter((slot) => slot.document === null);

  return (
    <div className="sp-ct-sg" data-testid="ct-sg">
      <div className="sp-ct-sg-notes">
        {readOnly ? (
          <div className="sp-ct-sg-lock" data-testid="ct-sg-readonly">
            <Lock size="0.75rem" aria-hidden="true" />
            <span>{t("content.signatures.leadReadOnly")}</span>
            <Button
              size="xs"
              variant="secondary"
              onClick={onCopy}
              data-testid="ct-sg-copy"
            >
              {t("content.signatures.copy")}
            </Button>
          </div>
        ) : (
          <p className="sp-ct-sg-lead">
            {t("content.signatures.lead")}{" "}
            {loaded.build?.anchors_known
              ? t("content.signatures.hintFollow")
              : t("content.signatures.hintNoFollow")}
          </p>
        )}
        {stale && (
          <Notice
            tone="warn"
            role="status"
            text={t("content.signatures.stale")}
          />
        )}
        {error && !staleError && (
          <Notice
            tone="err"
            role="alert"
            text={
              <span data-testid="ct-sg-save-error">
                {packErrorText(error)}
                {reason && (
                  <span className="sp-ct-sg-reason mono">{reason}</span>
                )}
              </span>
            }
          />
        )}
      </div>
      <div className="sp-ct-sg-body">
        <div className="sp-ct-sg-pdf" data-testid="ct-sg-pdf">
          <PdfStampEditor
            projectId=""
            docId={stamper.document}
            pdfRelPath={documentName}
            pdfAvailable
            pdfUrl={pdfUrl}
            slotDefs={stamper.slotDefs}
            state={stamper.state}
            page={page}
            onPageChange={setPage}
            onPageCountChange={setPageCount}
            onPlacementChange={(slotId, change) => {
              const slot = slotOf(slotId);
              if (slot) send(placeOpFrom(slot, stamper.document, change));
            }}
            readOnly={readOnly || patch.isPending}
            {...(readOnly
              ? {}
              : {
                  onDateMarkChange: (
                    slotId: string,
                    index: number,
                    place: DateMarkPlace,
                  ) => {
                    const slot = slotOf(slotId);
                    if (slot)
                      send(
                        dateMoveOpFrom(slot, stamper.document, index, place),
                      );
                  },
                })}
            docLang={lang}
            mutedSlots={stamper.muted}
          />
        </div>
        <div className="sp-ct-sg-panel">
          <h2 className="sp-ct-sg-h2">{t("content.signatures.panel")}</h2>
          <p className="sp-ct-sg-note">{t("content.signatures.frameNote")}</p>
          <ul className="sp-ct-sg-list" data-testid="ct-sg-list">
            {applicable.map((slot) => (
              <PlaceCard
                key={slot.id}
                slot={slot}
                data={loaded}
                document={stamper.document}
                page={page}
                pageCount={pageCount}
                lang={lang}
                editable={!readOnly}
                pending={patch.isPending}
                onOp={send}
                onJump={setPage}
              />
            ))}
          </ul>
          {others.length > 0 && (
            <details className="sp-ct-sg-more" data-testid="ct-sg-others">
              <summary>
                {t("content.signatures.others", { count: others.length })}
              </summary>
              <ul className="sp-ct-sg-plain">
                {others.map((slot) => (
                  <li key={slot.id}>
                    {pickLocalized(slot.label, i18n.language, slot.id)}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
};
