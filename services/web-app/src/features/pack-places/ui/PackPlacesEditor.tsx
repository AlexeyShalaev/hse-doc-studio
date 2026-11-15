import { useMemo, useState } from "react";
import { clsx } from "clsx";
import { Maximize2 } from "lucide-react";
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
  PdfStampEditor,
  type DateMarkPlace,
} from "@features/signature-stamper";
import { ApiError } from "@shared/api";
import { Button, ErrorState, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  dateMoveOpFrom,
  placeOpFrom,
  stamperStateOf,
} from "../lib/placesState";
import { SlotCatalog } from "./SlotCatalog";

export type PackPlacesEditorProps = {
  workspaceId: string;
  versionRef: PackVersionRef;
  /** Удачная сборка предпросмотра: её PDF и якоря. */
  buildId: string;
  pdfUrl: string;
  /** Подпись документа над страницей. */
  documentLabel: string;
  /** Язык документа в комбинации: месяц в примере метки даты. */
  lang: string;
  /** Во весь экран: страница и каталог рядом. */
  wide?: boolean;
  onOpenWide?: () => void;
  /** Места записаны в манифест версии (`path`). */
  onSaved?: (path: string) => void;
};

/** Подпись рамки места по умолчанию: имя слота с пометкой в каждом языке. */
const withSuffix = (
  label: Record<string, string>,
  suffix: string,
): Record<string, string> =>
  Object.fromEntries(
    Object.entries(label).map(([lng, text]) => [lng, `${text} (${suffix})`]),
  );

/**
 * Места подписей и метки даты пака на PDF предпросмотра (template-studio.md, 5.6, срез T9). Рамки
 * слотов, применимых к документу, двигаются и тянутся тем же редактором, что у проекта; вместо
 * картинки подписи заглушка с именем слота. Каждая правка сразу пишется в `version.yaml` версии
 * точечной правкой; выпущенная версия только для просмотра.
 */
export const PackPlacesEditor = ({
  workspaceId,
  versionRef,
  buildId,
  pdfUrl,
  documentLabel,
  lang,
  wide = false,
  onOpenWide,
  onSaved,
}: PackPlacesEditorProps) => {
  const { t } = useTranslation("packStudio");
  const query = usePackSignatures(workspaceId, versionRef, buildId);
  const patch = usePatchPackSignatures(workspaceId, versionRef, buildId);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [stale, setStale] = useState(false);
  const data = query.data;
  const defaultSuffix = t("places.defaultFrame");
  const stamper = useMemo(
    () =>
      data
        ? stamperStateOf(data, (slot) =>
            slot.document?.kind === "default"
              ? withSuffix(slot.label, defaultSuffix)
              : slot.label,
          )
        : null,
    [data, defaultSuffix],
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
        testId="places-error"
      />
    );
  }
  if (!stamper) return null;

  const loaded = query.data;
  const readOnly = loaded.read_only !== null;
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

  return (
    <div
      className={clsx("ps-places", wide && "ps-places-wide")}
      data-testid="pack-places"
    >
      <div className="ps-places-notes">
        {readOnly ? (
          <Notice
            tone="info"
            role="status"
            text={
              <span data-testid="places-read-only">{t("places.readOnly")}</span>
            }
          />
        ) : (
          <p className="ps-slot-hint">
            {loaded.build?.anchors_known
              ? t("places.hintAnchors")
              : t("places.hintNoAnchors")}
          </p>
        )}
        {stale && <Notice tone="warn" role="status" text={t("places.stale")} />}
        {error && !staleError && (
          <Notice
            tone="err"
            role="alert"
            text={
              <span data-testid="places-save-error">
                {packErrorText(error)}
                {reason && (
                  <span className="ps-preview-detail mono">{reason}</span>
                )}
              </span>
            }
          />
        )}
        {!wide && onOpenWide && (
          <Button
            size="xs"
            variant="ghost"
            onClick={onOpenWide}
            data-testid="places-wide"
          >
            <Maximize2 size="0.6875rem" aria-hidden="true" />
            {t("places.wide")}
          </Button>
        )}
      </div>
      <div className="ps-places-body">
        <div className="ps-places-pdf" data-testid="places-pdf">
          <PdfStampEditor
            projectId=""
            docId={stamper.document}
            pdfRelPath={documentLabel}
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
        <div className="ps-places-panel">
          <p className="ps-slot-hint">{t("places.aspect")}</p>
          <SlotCatalog
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
        </div>
      </div>
    </div>
  );
};
