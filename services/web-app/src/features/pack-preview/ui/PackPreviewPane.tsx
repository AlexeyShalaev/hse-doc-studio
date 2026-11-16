import { useMemo, useState, type ReactNode } from "react";
import { CircleX, Eye, FileText, Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  errorNumber,
  packErrorText,
  packPreviewPdfUrl,
  usePackPreviewBuild,
  usePackPreviewOptions,
  useStartPackPreview,
  versionRefOf,
  type PackPreviewOptions,
  type PackVersionRef,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import {
  Button,
  EmptyState,
  ErrorState,
  Modal,
  PdfViewer,
  Select,
  Spinner,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  documentFits,
  effectiveCombination,
  effectiveVariant,
  exampleOf,
  variantFits,
  type Combination,
} from "../lib/combination";
import { selectionKey, usePreviewSelection } from "../lib/selection";
import { useSwitchText } from "../lib/switchText";
import { BuildView, LogModal, type BuildViewMode } from "./BuildView";

/** Что нужно вкладке «Места подписей» (срез T9): удачная сборка документа версии. */
export type PackPlacesSlot = {
  versionRef: PackVersionRef;
  buildId: string;
  pdfUrl: string;
  documentLabel: string;
  /** Язык комбинации: месяц в примере метки даты. */
  lang: string;
  /** Во весь экран: страница и каталог слотов рядом. */
  wide: boolean;
  onOpenWide: () => void;
};

export type PackPreviewPaneProps = {
  workspaceId: string;
  /** Открытый файл: предпросмотр собирает его версию шаблона. */
  path: string;
  /** Меняется после каждой записи: собранный PDF мог устареть. */
  revision: number;
  /** Места подписей на собранном PDF (страница передаёт редактор мест пака); без него только PDF. */
  places?: (slot: PackPlacesSlot) => ReactNode;
};

const Controls = ({
  options,
  example,
  onExample,
  combination,
  onSwitch,
  document,
  onDocument,
  variant,
  onVariant,
}: {
  options: PackPreviewOptions;
  example: string;
  onExample: (id: string) => void;
  combination: Combination;
  onSwitch: (id: string, value: string) => void;
  document: string;
  onDocument: (id: string) => void;
  /** Вариант документа, который уйдёт в сборку (срез O9); null: вариантов нет. */
  variant: string | null;
  onVariant: (id: string) => void;
}) => {
  const { t, i18n } = useTranslation("packStudio");
  const text = useSwitchText();
  const exampleLabel = (id: string, label: Record<string, string> | null) =>
    label ? pickLocalized(label, i18n.language, id) : id;
  const chosen = exampleOf(options, example);
  const variants =
    options.documents.find((doc) => doc.id === document)?.variants ?? [];
  const chosenVariant = variants.find((v) => v.id === variant);
  return (
    <div className="ps-preview-controls">
      <div className="field">
        <label>{t("preview.document")}</label>
        <Select
          value={document}
          onValueChange={onDocument}
          ariaLabel={t("preview.document")}
          options={options.documents.map((doc) => ({
            value: doc.id,
            label: documentFits(doc, combination)
              ? pickLocalized(doc.name, i18n.language, doc.id)
              : t("preview.documentOff", {
                  name: pickLocalized(doc.name, i18n.language, doc.id),
                }),
          }))}
        />
      </div>
      {variants.length > 1 && variant !== null && (
        <div className="field">
          <label>{t("preview.variant")}</label>
          <Select
            value={variant}
            onValueChange={onVariant}
            ariaLabel={t("preview.variant")}
            options={variants.map((v) => {
              const name = pickLocalized(v.label, i18n.language, v.id);
              return {
                value: v.id,
                label: variantFits(v, combination.lang)
                  ? name
                  : t("preview.variantLangs", {
                      name,
                      langs: v.langs.join(", "),
                    }),
                isDisabled: !variantFits(v, combination.lang),
              };
            })}
          />
          {chosenVariant && !chosenVariant.pdf && (
            <p className="hint">{t("preview.variantNoPdf")}</p>
          )}
        </div>
      )}
      <div className="field">
        <label>{t("preview.example")}</label>
        <Select
          value={example}
          onValueChange={onExample}
          ariaLabel={t("preview.example")}
          options={options.examples.map((item) => ({
            value: item.id,
            label:
              item.source === "auto"
                ? t("preview.autoExample", {
                    name: exampleLabel(item.id, item.label),
                  })
                : exampleLabel(item.id, item.label),
            isDisabled: item.error !== null,
          }))}
        />
        {chosen?.error && (
          <p className="hint ps-problem-error">{chosen.error}</p>
        )}
      </div>
      {options.switches.length > 0 && (
        <details className="sync-details" open>
          <summary>{t("preview.switches")}</summary>
          <div className="ps-preview-switches">
            {options.switches.map((sw) => (
              <div className="field" key={sw.id}>
                <label>{text.label(sw)}</label>
                <Select
                  value={combination[sw.id] ?? sw.default}
                  onValueChange={(value) => {
                    onSwitch(sw.id, value);
                  }}
                  ariaLabel={text.label(sw)}
                  options={sw.values.map((value) => ({
                    value,
                    label: text.value(sw, value),
                  }))}
                />
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
};

const PreviewForVersion = ({
  workspaceId,
  versionRef,
  revision,
  places,
}: {
  workspaceId: string;
  versionRef: PackVersionRef;
  revision: number;
  places: PackPreviewPaneProps["places"];
}) => {
  const { t, i18n } = useTranslation("packStudio");
  const [mode, setMode] = useState<BuildViewMode>("pdf");
  const options = usePackPreviewOptions(workspaceId, versionRef);
  const start = useStartPackPreview(workspaceId);
  // Набор и переключатели общие с «Маршрутом в этой комбинации» формы точек (срез T13).
  const {
    selection: { example, overrides, variants },
    setExample,
    setSwitch,
    setVariant,
    reset,
  } = usePreviewSelection(selectionKey(workspaceId, versionRef));
  const [document, setDocument] = useState<string | null>(null);
  const [buildId, setBuildId] = useState<string | null>(null);
  const [builtAt, setBuiltAt] = useState(revision);
  const [logFor, setLogFor] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const build = usePackPreviewBuild(workspaceId, buildId);

  const data = options.data;
  const chosenExample = data ? exampleOf(data, example) : null;
  const combination = useMemo(
    () => (data ? effectiveCombination(data, chosenExample, overrides) : {}),
    [data, chosenExample, overrides],
  );

  if (options.isPending) {
    return (
      <div className="flex justify-center" style={{ padding: "1.5rem" }}>
        <Spinner size="md" />
      </div>
    );
  }
  if (options.isError) {
    const reason =
      options.error instanceof ApiError &&
      typeof options.error.data?.reason === "string"
        ? options.error.data.reason
        : null;
    return (
      <ErrorState
        compact
        description={
          <>
            {packErrorText(options.error)}
            {reason && <span className="ps-preview-detail mono">{reason}</span>}
          </>
        }
        onRetry={() => void options.refetch()}
        testId="preview-options-error"
      />
    );
  }

  const opts = options.data;
  const exampleId = chosenExample?.id ?? opts.default_example;
  const fitting = opts.documents.filter((doc) =>
    documentFits(doc, combination),
  );
  const documentId =
    document ?? fitting[0]?.id ?? opts.documents[0]?.id ?? null;

  if (documentId === null) {
    return (
      <EmptyState
        compact
        icon={<FileText size="1.25rem" />}
        title={t("preview.noDocuments")}
        testId="preview-no-documents"
      />
    );
  }

  const documentDef = opts.documents.find((doc) => doc.id === documentId);
  const variant = documentDef
    ? effectiveVariant(documentDef, variants[documentId], combination.lang)
    : null;

  const run = () => {
    start.mutate(
      {
        ref: versionRef,
        body: {
          documents: [documentId],
          example: exampleId,
          combination,
          // Только у документа с вариантами; прежний сервер поля не знает и вариантов не отдаёт.
          ...(variant !== null && { variant }),
        },
      },
      {
        onSuccess: (builds) => {
          const first = builds[0];
          if (first) {
            setBuildId(first.id);
            setBuiltAt(revision);
          }
        },
      },
    );
  };

  const running =
    build.data?.status === "queued" || build.data?.status === "running";
  const built = build.data?.status === "succeeded" ? build.data : null;
  const builtDoc = built
    ? opts.documents.find((doc) => doc.id === built.document)
    : undefined;
  const placesFor = (wide: boolean): ReactNode =>
    built && places
      ? places({
          versionRef,
          buildId: built.id,
          pdfUrl: packPreviewPdfUrl(workspaceId, built.id),
          documentLabel: builtDoc
            ? pickLocalized(builtDoc.name, i18n.language, built.document)
            : built.document,
          lang: built.combination.lang ?? combination.lang ?? "ru",
          wide,
          onOpenWide: () => {
            setFull(true);
          },
        })
      : null;
  const fullPlaces = full && mode === "places" ? placesFor(true) : null;
  const startError = start.error;
  const quota =
    startError instanceof ApiError && startError.code === "preview_quota";
  const invalidField =
    startError instanceof ApiError && startError.code === "preview_invalid"
      ? [startError.data?.field, startError.data?.value]
          .filter((v) => typeof v === "string")
          .join(" = ")
      : "";

  return (
    <div className="ps-preview" data-testid="preview-pane">
      <Controls
        options={opts}
        example={exampleId}
        onExample={(id) => {
          setExample(id);
        }}
        combination={combination}
        onSwitch={setSwitch}
        document={documentId}
        onDocument={setDocument}
        variant={variant}
        onVariant={(id) => {
          setVariant(documentId, id);
        }}
      />
      <div className="ps-preview-run">
        <Button
          size="sm"
          disabled={start.isPending || running || chosenExample?.error != null}
          onClick={run}
          data-testid="preview-build"
        >
          {start.isPending ? <Spinner size="sm" /> : <Play size="0.75rem" />}
          {build.data ? t("preview.rebuild") : t("preview.build")}
        </Button>
        {(Object.keys(overrides).length > 0 ||
          Object.keys(variants).length > 0) && (
          <Button size="sm" variant="ghost" onClick={reset}>
            <CircleX size="0.75rem" />
            {t("preview.resetSwitches")}
          </Button>
        )}
      </div>
      {startError && (
        <Notice
          tone={quota ? "warn" : "err"}
          role="alert"
          text={
            quota
              ? t("preview.quota", {
                  limit: errorNumber(startError, "limit") ?? 2,
                })
              : [packErrorText(startError), invalidField]
                  .filter(Boolean)
                  .join(" ")
          }
        />
      )}
      {build.isError && (
        <Notice tone="err" role="alert" text={packErrorText(build.error)} />
      )}
      {build.data ? (
        <BuildView
          workspaceId={workspaceId}
          build={build.data}
          stale={builtAt !== revision}
          onLog={() => {
            setLogFor(build.data.id);
          }}
          onFull={() => {
            setFull(true);
          }}
          places={placesFor(false)}
          mode={mode}
          onMode={setMode}
        />
      ) : (
        <p className="ps-pane-empty">{t("preview.hint")}</p>
      )}
      <LogModal
        workspaceId={workspaceId}
        buildId={logFor}
        onClose={() => {
          setLogFor(null);
        }}
      />
      <Modal
        isOpen={full && build.data?.status === "succeeded"}
        onClose={() => {
          setFull(false);
        }}
        title={fullPlaces ? t("places.title") : t("preview.title")}
        width={fullPlaces ? 1240 : 980}
      >
        {fullPlaces ??
          (build.data?.status === "succeeded" && (
            <div style={{ height: "75vh", minHeight: "20rem" }}>
              <PdfViewer
                url={packPreviewPdfUrl(workspaceId, build.data.id)}
                refreshKey={build.data.id}
                ariaLabel={build.data.document}
              />
            </div>
          ))}
      </Modal>
    </div>
  );
};

/**
 * Вкладка «Предпросмотр» (template-studio.md, 6): сборка документа версии на
 * тестовых данных (examples/*.yaml или автонаборы) в выбранной комбинации
 * переключателей. Сборка в очереди опрашивается, её можно отменить; готовый PDF
 * открывается тут же или во весь экран, журнал рядом.
 */
export const PackPreviewPane = ({
  workspaceId,
  path,
  revision,
  places,
}: PackPreviewPaneProps) => {
  const { t } = useTranslation("packStudio");
  const ref = versionRefOf(path);
  if (ref === null) {
    return (
      <EmptyState
        compact
        icon={<Eye size="1.25rem" />}
        title={t("preview.title")}
        description={t("preview.outside")}
        testId="preview-outside"
      />
    );
  }
  return (
    <PreviewForVersion
      key={`${ref.pack}/${ref.template}/${ref.version}`}
      workspaceId={workspaceId}
      versionRef={ref}
      revision={revision}
      places={places}
    />
  );
};
