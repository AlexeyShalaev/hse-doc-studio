import { useMemo, useState, type ReactNode } from "react";
import {
  CircleX,
  Eye,
  FileText,
  Maximize2,
  PenLine,
  Play,
  ScrollText,
  Square,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  errorNumber,
  packErrorText,
  packPreviewPdfUrl,
  useCancelPackPreview,
  usePackPreviewBuild,
  usePackPreviewLog,
  usePackPreviewOptions,
  useStartPackPreview,
  versionRefOf,
  type PackPreviewBuild,
  type PackPreviewOptions,
  type PackPreviewSwitch,
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
  exampleOf,
  type Combination,
} from "../lib/combination";

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

type BuildViewMode = "pdf" | "places";

const KNOWN_SWITCHES = new Set([
  "lang",
  "kind",
  "staffing",
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
  "nda",
]);

const KNOWN_VALUES = new Set([
  "solo",
  "team2",
  "team3",
  "university",
  "company",
  "none",
  "yes",
  "no",
]);

/** Подпись переключателя: своя у поля анкеты, иначе из словаря. */
const useSwitchText = () => {
  const { t, i18n } = useTranslation("packStudio");
  return {
    label: (sw: PackPreviewSwitch): string =>
      sw.label
        ? pickLocalized(sw.label, i18n.language, sw.id)
        : KNOWN_SWITCHES.has(sw.id)
          ? t(`preview.switch.${sw.id}`)
          : sw.id.replace(/^meta\./, ""),
    value: (sw: PackPreviewSwitch, value: string): string =>
      sw.id === "lang"
        ? value.toUpperCase()
        : sw.id !== "kind" && KNOWN_VALUES.has(value)
          ? t(`preview.value.${value}`)
          : value,
  };
};

/** Текст неудачной сборки: свой для кодов предпросмотра, затем общий словарь ошибок. */
const useBuildErrorText = () => {
  const { t, i18n } = useTranslation("packStudio");
  return (code: string): string => {
    if (i18n.exists(`packStudio:preview.error.${code}`)) {
      return t(`preview.error.${code}`);
    }
    if (i18n.exists(`errors:code.${code}`)) return t(`errors:code.${code}`);
    return t("preview.error.generic", { code });
  };
};

const LogModal = ({
  workspaceId,
  buildId,
  onClose,
}: {
  workspaceId: string;
  buildId: string | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packStudio");
  const log = usePackPreviewLog(workspaceId, buildId);
  return (
    <Modal
      isOpen={buildId !== null}
      onClose={onClose}
      title={t("preview.log")}
      width={820}
    >
      {log.isPending ? (
        <div className="flex justify-center" style={{ padding: "2rem" }}>
          <Spinner size="md" />
        </div>
      ) : log.isError ? (
        <ErrorState
          compact
          description={packErrorText(log.error)}
          onRetry={() => void log.refetch()}
        />
      ) : (
        <pre className="ps-log mono" data-testid="preview-log">
          {log.data || t("preview.logEmpty")}
        </pre>
      )}
    </Modal>
  );
};

/** Сборка: очередь, идёт, готова (PDF), не удалась, отменена. */
const BuildView = ({
  workspaceId,
  build,
  stale,
  onLog,
  onFull,
  places,
  mode,
  onMode,
}: {
  workspaceId: string;
  build: PackPreviewBuild;
  stale: boolean;
  onLog: () => void;
  onFull: () => void;
  places: ReactNode;
  mode: BuildViewMode;
  onMode: (mode: BuildViewMode) => void;
}) => {
  const { t } = useTranslation("packStudio");
  const cancel = useCancelPackPreview(workspaceId);
  const errorText = useBuildErrorText();

  if (build.status === "queued" || build.status === "running") {
    return (
      <div className="ps-preview-state" data-testid="preview-running">
        <Spinner size="sm" />
        <span>{t(`preview.status.${build.status}`)}</span>
        <Button
          size="xs"
          variant="ghost"
          disabled={cancel.isPending}
          onClick={() => {
            cancel.mutate(build.id);
          }}
          data-testid="preview-cancel"
        >
          <Square size="0.6875rem" />
          {t("preview.cancel")}
        </Button>
        {cancel.isError && (
          <Notice tone="err" role="alert" text={packErrorText(cancel.error)} />
        )}
      </div>
    );
  }
  if (build.status === "cancelled") {
    return (
      <p className="ps-pane-empty" data-testid="preview-cancelled">
        {t("preview.status.cancelled")}
      </p>
    );
  }
  if (build.status === "failed") {
    return (
      <div className="flex flex-col" style={{ gap: "0.5rem" }}>
        <Notice
          tone="err"
          role="alert"
          text={
            <span data-testid="preview-failed">
              {errorText(build.error?.code ?? "unknown")}
              {build.error?.detail && (
                <span className="ps-preview-detail mono">
                  {build.error.detail}
                </span>
              )}
            </span>
          }
          action={
            <Button
              size="xs"
              variant="secondary"
              onClick={onLog}
              data-testid="preview-failed-log"
            >
              <ScrollText size="0.6875rem" />
              {t("preview.log")}
            </Button>
          }
        />
      </div>
    );
  }
  const showPlaces = mode === "places" && places !== null;
  return (
    <div className="ps-preview-pdf" data-testid="preview-pdf">
      {places !== null && (
        <div
          className="ps-view-tabs ps-preview-modes"
          role="tablist"
          aria-label={t("places.modes")}
        >
          <button
            type="button"
            role="tab"
            aria-selected={!showPlaces}
            className={showPlaces ? "ps-view-tab" : "ps-view-tab active"}
            onClick={() => {
              onMode("pdf");
            }}
            data-testid="preview-mode-pdf"
          >
            <FileText size="0.75rem" aria-hidden="true" />
            {t("places.modePdf")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={showPlaces}
            className={showPlaces ? "ps-view-tab active" : "ps-view-tab"}
            onClick={() => {
              onMode("places");
            }}
            data-testid="preview-mode-places"
          >
            <PenLine size="0.75rem" aria-hidden="true" />
            {t("places.title")}
          </button>
        </div>
      )}
      <div className="ps-preview-meta">
        <span>
          {[
            build.pages !== null
              ? t("preview.pages", { count: build.pages })
              : null,
            build.cached ? t("preview.cached") : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
        <span className="ps-editor-actions">
          <Button
            size="xs"
            variant="ghost"
            onClick={onLog}
            data-testid="preview-log-open"
          >
            <ScrollText size="0.6875rem" />
            {t("preview.log")}
          </Button>
          <Button
            size="xs"
            variant="ghost"
            onClick={onFull}
            title={t("preview.full")}
            aria-label={t("preview.full")}
            data-testid="preview-full"
          >
            <Maximize2 size="0.6875rem" />
          </Button>
        </span>
      </div>
      {stale && <Notice tone="info" role="status" text={t("preview.stale")} />}
      {showPlaces ? (
        places
      ) : (
        <div className="ps-preview-viewer">
          <PdfViewer
            url={packPreviewPdfUrl(workspaceId, build.id)}
            refreshKey={build.id}
            ariaLabel={build.document}
            initialFit
          />
        </div>
      )}
    </div>
  );
};

const Controls = ({
  options,
  example,
  onExample,
  combination,
  onSwitch,
  document,
  onDocument,
}: {
  options: PackPreviewOptions;
  example: string;
  onExample: (id: string) => void;
  combination: Combination;
  onSwitch: (id: string, value: string) => void;
  document: string;
  onDocument: (id: string) => void;
}) => {
  const { t, i18n } = useTranslation("packStudio");
  const text = useSwitchText();
  const exampleLabel = (id: string, label: Record<string, string> | null) =>
    label ? pickLocalized(label, i18n.language, id) : id;
  const chosen = exampleOf(options, example);
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
  const [example, setExample] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Combination>({});
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

  const run = () => {
    start.mutate(
      {
        ref: versionRef,
        body: {
          documents: [documentId],
          example: exampleId,
          combination,
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
        onSwitch={(id, value) => {
          setOverrides((prev) => ({ ...prev, [id]: value }));
        }}
        document={documentId}
        onDocument={setDocument}
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
        {Object.keys(overrides).length > 0 && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setOverrides({});
            }}
          >
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
