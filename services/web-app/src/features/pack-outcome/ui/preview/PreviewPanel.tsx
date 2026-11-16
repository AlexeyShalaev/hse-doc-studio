import { useEffect, useId, useRef, useState } from "react";
import { Play, RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackFilesRevision,
  usePackPreviewOptions,
  type PackPreviewOptions,
} from "@entities/pack-studio";
import {
  BuildView,
  LogModal,
  PdfFullModal,
  usePreviewRunner,
  variantFits,
} from "@features/pack-preview";
import { ApiError } from "@shared/api";
import { pickLocalized, useDebouncedValue } from "@shared/lib";
import { Button, ErrorState, Select, Spinner } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { Notice } from "@shared/ui/ConflictKit";
import {
  INPUTS_SOURCE,
  filesKeyOf,
  previewTarget,
  runKeyOf,
  staleByFiles,
  type PreviewSource,
} from "../../lib/previewRequest";
import { scenarioName } from "../../lib/scenarios";
import {
  readPreviewMemory,
  useAutoPreview,
  writePreviewMemory,
} from "../../lib/previewStore";
import { useOutcomeModel } from "../../model";
import { BuildInfo } from "./BuildInfo";

/** Пауза после последней смены вводных, сценария или файлов до автосборки. */
export const AUTO_DEBOUNCE_MS = 700;
/** Через сколько секунд автосборка повторяет запуск после отказа «слишком много сборок». */
export const QUOTA_RETRY_S = 10;

const AUTO_VARIANT = "__auto__";
const INPUTS_VALUE = "inputs";
const SCENARIO_PREFIX = "scenario:";

const sourceValue = (source: PreviewSource): string =>
  source.kind === "inputs" ? INPUTS_VALUE : `${SCENARIO_PREFIX}${source.id}`;

const fieldDetail = (error: unknown): string => {
  if (!(error instanceof ApiError) || error.code !== "preview_invalid") {
    return "";
  }
  const { field, value, reason } = error.data ?? {};
  return [
    [field, value].filter((v) => typeof v === "string").join(" = "),
    typeof reason === "string" ? `(${reason})` : "",
  ]
    .filter(Boolean)
    .join(" ");
};

/** Обратный отсчёт до повторной сборки после отказа по числу одновременных сборок. */
export const QuotaCountdown = ({ onDone }: { onDone: () => void }) => {
  const { t } = useTranslation("packOutcome");
  const [left, setLeft] = useState(QUOTA_RETRY_S);
  const fired = useRef(false);
  useEffect(() => {
    const timer = setInterval(() => {
      setLeft((n) => Math.max(0, n - 1));
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    if (left === 0 && !fired.current) {
      fired.current = true;
      onDone();
    }
  }, [left, onDone]);
  return (
    // Секунды идут внутри предупреждения: каждую программа экрана читать не должна.
    <span aria-live="off" data-testid="outcome-preview-countdown">
      {t("preview.quotaRetry", { seconds: left })}
    </span>
  );
};

type Props = {
  /** Документ результата (его id и у документа предпросмотра). */
  document: string;
  /** Явное открытие: собрать сразу, не дожидаясь автосборки. */
  buildOnMount: boolean;
  memoryKey: string;
};

/**
 * Предпросмотр PDF документа результата (срез F12): выбор варианта, источника вводных (текущие
 * или сценарий) и набора данных; сборка по кнопке и автосборка после правок. Собирает сервер
 * (тот же эндпоинт, что вкладка «Предпросмотр» в «Файлах»), условий клиент не считает.
 */
export const PreviewPanel = ({ document, buildOnMount, memoryKey }: Props) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { workspaceId, ref, url, shown, scenarios, inputs } = model;
  const options = usePackPreviewOptions(workspaceId, ref);
  const filesRevision = usePackFilesRevision(workspaceId);
  const [auto, setAuto] = useAutoPreview();
  // Память читается один раз: дальше панель сама источник правды и пишет в неё.
  const [memory] = useState(() => readPreviewMemory(memoryKey));
  const runner = usePreviewRunner(
    workspaceId,
    ref,
    memory.document === document ? memory.built : null,
  );
  const [source, setSource] = useState<PreviewSource>(memory.source);
  const [variants, setVariants] = useState<Record<string, string>>({
    ...memory.variants,
  });
  const [logFor, setLogFor] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const ids = useId();

  const lang = i18n.language;
  const entries = scenarios.data?.scenarios;
  const usable = (entries ?? []).filter((e) => e.scenario !== null);
  // Сценарий могли удалить: тогда источник возвращается к текущим вводным.
  const scenarioEntry =
    source.kind === "scenario"
      ? usable.find((e) => e.id === source.id)
      : undefined;
  const effective: PreviewSource =
    source.kind === "scenario" && scenarioEntry === undefined && entries
      ? INPUTS_SOURCE
      : source;

  const opts: PackPreviewOptions | undefined = options.data;
  const scenarioLang =
    scenarioEntry?.scenario?.inputs.lang ?? inputs.data?.defaults.lang;
  const target =
    opts && shown
      ? previewTarget({
          options: opts,
          document,
          source: effective,
          variantPick: variants[document] ?? null,
          inputs: shown.inputs,
          example: url.state.example,
          shownExample: shown.example,
          scenarioLang,
        })
      : null;

  const filesKey = filesKeyOf({
    revision: shown?.revision ?? "",
    scenarioEtag: scenarioEntry?.etag ?? "",
    filesRevision,
  });
  const fullKey = target ? runKeyOf(target, filesKey) : "";
  const debouncedKey = useDebouncedValue(fullKey, AUTO_DEBOUNCE_MS);

  const exampleError =
    opts?.examples.find(
      (e) =>
        e.id ===
        (target?.body?.example ??
          scenarioEntry?.scenario?.example ??
          opts.default_example),
    )?.error ?? null;
  const body = target?.body ?? null;
  const ready = body !== null && exampleError === null;

  const pendingOpen = useRef(buildOnMount);
  const { start, attemptedKey } = runner;
  useEffect(() => {
    if (!ready) return;
    if (pendingOpen.current) {
      pendingOpen.current = false;
      start(body, fullKey);
      return;
    }
    if (!auto || debouncedKey !== fullKey || attemptedKey === fullKey) return;
    start(body, fullKey);
  }, [ready, body, auto, debouncedKey, fullKey, attemptedKey, start]);

  // Слишком много сборок сразу: мягкий отказ, при автосборке повтор через несколько секунд.
  const startError = runner.startError;
  const quota =
    startError instanceof ApiError && startError.code === "preview_quota";

  // Закрытая панель не держит сборку: идущая отменяется, место в очереди освобождается.
  const live = useRef({ running: false, cancel: runner.cancel });
  useEffect(() => {
    live.current = { running: runner.running, cancel: runner.cancel };
  }, [runner.running, runner.cancel]);
  useEffect(
    () => () => {
      if (live.current.running) live.current.cancel();
    },
    [],
  );

  const { build, builtKey } = runner;
  useEffect(() => {
    writePreviewMemory(memoryKey, {
      document,
      source,
      variants,
      built:
        runner.buildId !== null && builtKey !== null
          ? { buildId: runner.buildId, key: builtKey }
          : null,
    });
  }, [memoryKey, document, source, variants, runner.buildId, builtKey]);

  if (options.isPending) {
    return (
      <div className="po-preview-wait" data-testid="outcome-preview-loading">
        <Spinner size="md" />
      </div>
    );
  }
  if (opts === undefined) {
    return (
      <ErrorState
        compact
        description={packErrorText(options.error)}
        onRetry={() => void options.refetch()}
        testId="outcome-preview-options-error"
      />
    );
  }
  if (target?.doc === null) {
    return (
      <p className="po-preview-note" data-testid="outcome-preview-no-document">
        {t("preview.noDocument")}
      </p>
    );
  }

  const doc = target?.doc ?? null;
  const docVariants = doc?.variants ?? [];
  const pickedVariant = variants[document];
  const stale =
    build?.status === "succeeded" &&
    builtKey !== null &&
    fullKey !== "" &&
    builtKey !== fullKey;
  const byFiles = stale && staleByFiles(builtKey, filesKey);
  const chosenVariant = docVariants.find(
    (v) => v.id === (pickedVariant ?? target?.variant),
  );
  const exampleValue =
    url.state.example ??
    (effective.kind === "scenario" ? scenarioEntry?.scenario?.example : null) ??
    shown?.example ??
    opts.default_example;
  const started = runner.starting;
  const retry = () => {
    if (body !== null) start(body, fullKey);
  };
  const buildDisabled = !ready || started || (runner.running && !stale);
  const status = !build
    ? ""
    : build.status === "succeeded"
      ? t("preview.live.done", { count: build.pages ?? 0 })
      : build.status === "failed"
        ? t("preview.live.failed")
        : build.status === "cancelled"
          ? t("preview.live.cancelled")
          : t("preview.live.running");

  return (
    <div className="po-preview-body" data-testid="outcome-preview">
      <p className="po-preview-lead">{t("preview.lead")}</p>

      <div className="po-preview-controls">
        <div className="po-preview-field">
          <label htmlFor={`${ids}-source`}>{t("preview.source")}</label>
          <Select
            id={`${ids}-source`}
            value={sourceValue(effective)}
            ariaLabel={t("preview.source")}
            onValueChange={(value) => {
              setSource(
                value.startsWith(SCENARIO_PREFIX)
                  ? {
                      kind: "scenario",
                      id: value.slice(SCENARIO_PREFIX.length),
                    }
                  : INPUTS_SOURCE,
              );
            }}
            options={[
              { value: INPUTS_VALUE, label: t("preview.sourceInputs") },
              ...usable.map((entry) => ({
                value: `${SCENARIO_PREFIX}${entry.id}`,
                label: t("preview.sourceScenario", {
                  name: scenarioName(entry, lang),
                }),
              })),
            ]}
          />
        </div>

        {docVariants.length > 1 && (
          <div className="po-preview-field">
            <label htmlFor={`${ids}-variant`}>{t("preview.variant")}</label>
            <Select
              id={`${ids}-variant`}
              value={
                effective.kind === "scenario"
                  ? (chosenVariant?.id ?? AUTO_VARIANT)
                  : (target?.variant ?? AUTO_VARIANT)
              }
              ariaLabel={t("preview.variant")}
              onValueChange={(value) => {
                setVariants((prev) => {
                  const rest = Object.fromEntries(
                    Object.entries(prev).filter(([id]) => id !== document),
                  );
                  return value === AUTO_VARIANT
                    ? rest
                    : { ...rest, [document]: value };
                });
              }}
              options={[
                {
                  value: AUTO_VARIANT,
                  label:
                    effective.kind === "scenario"
                      ? t("preview.variantFromScenario")
                      : t("preview.variantFromInputs"),
                  isDisabled: effective.kind === "inputs",
                },
                ...docVariants.map((v) => {
                  const name = pickLocalized(v.label, lang, v.id);
                  const fits = variantFits(v, target?.lang);
                  return {
                    value: v.id,
                    label: fits
                      ? name
                      : t("preview.variantOnly", {
                          name,
                          langs: v.langs.join(", "),
                        }),
                    isDisabled: !fits,
                  };
                }),
              ]}
            />
            {chosenVariant && !chosenVariant.pdf && (
              <p
                className="po-preview-hint"
                data-testid="outcome-preview-nopdf"
              >
                {t("preview.variantNoPdf")}
              </p>
            )}
            {docVariants.some((v) => !variantFits(v, target?.lang)) && (
              <p className="po-preview-hint">
                {t("preview.variantLangHint", { lang: target?.lang ?? "" })}
              </p>
            )}
          </div>
        )}

        <div className="po-preview-field">
          <label htmlFor={`${ids}-example`}>{t("preview.example")}</label>
          <Select
            id={`${ids}-example`}
            value={exampleValue}
            ariaLabel={t("preview.example")}
            onValueChange={(value) => {
              url.update({ example: value });
            }}
            options={opts.examples.map((e) => ({
              value: e.id,
              label: e.label ? pickLocalized(e.label, lang, e.id) : e.id,
              isDisabled: e.error !== null,
            }))}
          />
          {exampleError !== null && (
            <p className="po-preview-hint" role="alert">
              {exampleError}
            </p>
          )}
        </div>
      </div>

      <div className="po-preview-run">
        <Button
          size="sm"
          disabled={buildDisabled}
          onClick={retry}
          data-testid="outcome-preview-build"
        >
          {started ? (
            <Spinner size="sm" />
          ) : build ? (
            <RotateCw size="0.75rem" aria-hidden="true" />
          ) : (
            <Play size="0.75rem" aria-hidden="true" />
          )}
          {build ? t("preview.rebuild") : t("preview.build")}
        </Button>
        <span className="po-preview-auto">
          <Switch
            id={`${ids}-auto`}
            checked={auto}
            onChange={setAuto}
            testId="outcome-preview-auto"
            describedBy={`${ids}-auto-hint`}
          />
          <label htmlFor={`${ids}-auto`}>{t("preview.auto")}</label>
        </span>
        <span id={`${ids}-auto-hint`} className="po-preview-hint">
          {t("preview.autoHint")}
        </span>
      </div>

      {startError !== null && startError !== undefined && (
        <Notice
          tone={quota ? "warn" : "err"}
          role="alert"
          text={
            <span data-testid="outcome-preview-start-error">
              {[
                quota
                  ? t("preview.quota", {
                      limit:
                        startError instanceof ApiError &&
                        typeof startError.data?.limit === "number"
                          ? startError.data.limit
                          : 2,
                    })
                  : packErrorText(startError),
                fieldDetail(startError),
              ]
                .filter(Boolean)
                .join(" ")}
              {quota && auto && target?.body && (
                <>
                  {" "}
                  <QuotaCountdown key={runner.attempts} onDone={retry} />
                </>
              )}
            </span>
          }
          action={
            quota ? (
              <Button
                size="xs"
                variant="secondary"
                disabled={!ready || started}
                onClick={retry}
                data-testid="outcome-preview-retry"
              >
                {t("preview.retryNow")}
              </Button>
            ) : undefined
          }
        />
      )}
      {runner.buildError !== null && runner.buildError !== undefined && (
        <Notice
          tone="err"
          role="alert"
          text={packErrorText(runner.buildError)}
        />
      )}
      {stale && (
        <Notice
          tone="info"
          role="status"
          text={
            <span data-testid="outcome-preview-stale">
              {byFiles ? t("preview.staleFiles") : t("preview.staleInputs")}
            </span>
          }
        />
      )}

      {build ? (
        <>
          <BuildView
            workspaceId={workspaceId}
            build={build}
            stale={false}
            onLog={() => {
              setLogFor(build.id);
            }}
            onFull={() => {
              setFull(true);
            }}
            places={null}
            mode="pdf"
            onMode={() => undefined}
          />
          {build.status === "succeeded" && (
            <>
              {build.cached && (
                <p
                  className="po-preview-hint"
                  data-testid="outcome-preview-cached"
                >
                  {t("preview.cachedLead")}
                </p>
              )}
              <BuildInfo
                build={build}
                doc={doc}
                scenarioName={
                  build.scenario == null
                    ? null
                    : (() => {
                        const entry = usable.find(
                          (e) => e.id === build.scenario,
                        );
                        return entry ? scenarioName(entry, lang) : null;
                      })()
                }
              />
            </>
          )}
        </>
      ) : (
        <p className="po-preview-note" data-testid="outcome-preview-hint">
          {t("preview.hint")}
        </p>
      )}

      <div className="sr-only" role="status" aria-live="polite">
        {status}
      </div>
      <LogModal
        workspaceId={workspaceId}
        buildId={logFor}
        onClose={() => {
          setLogFor(null);
        }}
      />
      <PdfFullModal
        workspaceId={workspaceId}
        build={build}
        isOpen={full}
        onClose={() => {
          setFull(false);
        }}
      />
    </div>
  );
};
