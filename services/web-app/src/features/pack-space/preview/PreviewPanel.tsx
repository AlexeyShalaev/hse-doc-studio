import { useId, useState, type ReactNode } from "react";
import { FileX2, Maximize2, Play, RotateCw, ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import { BuildView, LogModal, PdfFullModal } from "@features/pack-preview";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import { Button, EmptyState, ErrorState, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useSpace } from "../context/SpaceContext";
import { Conditions } from "./Conditions";
import { Findings } from "./Findings";
import { usePreviewBuild, type PreviewBuild } from "./usePreviewBuild";
import "./space-preview.css";

/** Почему сборка не удалась, словами: свой текст для известных кодов, затем общий словарь ошибок. */
const useReason = () => {
  const { t, i18n } = useTranslation("packSpace");
  return (code: string): string => {
    if (i18n.exists(`preview.error.${code}`, { ns: "packSpace" })) {
      return t(`preview.error.${code}`);
    }
    if (i18n.exists(`errors:code.${code}`)) return t(`errors:code.${code}`);
    return t("preview.error.generic", { code });
  };
};

const fieldDetail = (error: unknown): string =>
  error instanceof ApiError && error.code === "preview_invalid"
    ? [error.data?.field, error.data?.value]
        .filter((part): part is string => typeof part === "string")
        .join(" = ")
    : "";

const Wait = ({ text, children }: { text: string; children?: ReactNode }) => (
  <div className="sp-pv-wait" role="status" data-testid="sp-pv-building">
    <Spinner size="sm" />
    <span>{text}</span>
    {children}
  </div>
);

type StateProps = {
  pv: PreviewBuild;
  onLog: () => void;
  onFull: () => void;
};

/** Одно состояние предпросмотра: страница, ожидание или понятное объяснение. */
const PreviewState = ({ pv, onLog, onFull }: StateProps) => {
  const { t } = useTranslation("packSpace");
  const reason = useReason();
  const { workspace } = useSpace();
  const { view } = pv;
  switch (view.kind) {
    case "loading":
      return <Wait text={t("preview.loading")} />;
    case "unavailable":
      return (
        <ErrorState
          compact
          title={t("preview.failedPrepare")}
          description={view.error ? packErrorText(view.error) : undefined}
          onRetry={view.retry}
          testId="sp-pv-unavailable"
        />
      );
    case "noPdf":
      return (
        <EmptyState
          compact
          icon={<FileX2 size="1.25rem" />}
          title={t("preview.noPdf.title")}
          description={t("preview.noPdf.lead")}
          testId="sp-pv-nopdf"
        />
      );
    case "notInKit": {
      const action = view.reason?.action ?? null;
      const reasonText = view.reason?.text ?? "";
      return (
        <EmptyState
          compact
          icon={<FileX2 size="1.25rem" />}
          title={t("preview.notInKit.title")}
          description={
            reasonText === "" ? t("preview.notInKit.lead") : reasonText
          }
          action={
            <span className="sp-pv-row">
              {action ? (
                <Button
                  size="sm"
                  onClick={() => {
                    pv.setInput(action.input, action.value);
                  }}
                  data-testid="sp-pv-show"
                >
                  {t("preview.notInKit.show", { condition: action.label })}
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="secondary"
                onClick={pv.resetSituation}
                data-testid="sp-pv-reset"
              >
                {t("preview.notInKit.reset")}
              </Button>
            </span>
          }
          testId="sp-pv-notinkit"
        />
      );
    }
    case "building":
      return (
        <Wait text={t("preview.building")}>
          {pv.running ? (
            <Button
              size="xs"
              variant="ghost"
              onClick={pv.cancel}
              data-testid="sp-pv-cancel"
            >
              {t("preview.cancel")}
            </Button>
          ) : null}
        </Wait>
      );
    case "ready":
      return (
        <div className="sp-pv-ready" data-testid="sp-pv-ready">
          {view.stale ? (
            <Notice
              tone="info"
              role="status"
              text={
                <span data-testid="sp-pv-stale">
                  {t(`preview.stale.${view.stale}`)}
                </span>
              }
            />
          ) : null}
          <BuildView
            workspaceId={workspace.id}
            build={view.build}
            stale={false}
            onLog={onLog}
            onFull={onFull}
            places={null}
            mode="pdf"
            onMode={() => undefined}
          />
        </div>
      );
    case "failed": {
      const code = view.build?.error?.code;
      const detail =
        view.error !== null
          ? [packErrorText(view.error), fieldDetail(view.error)]
              .filter(Boolean)
              .join(" ")
          : reason(code ?? "unknown");
      return (
        <Notice
          tone="err"
          role="alert"
          text={
            <span data-testid="sp-pv-failed">
              <b>{t("preview.failed.title")}.</b> {detail}
              {view.build ? (
                <>
                  {" "}
                  <span className="sp-pv-muted">{t("preview.errorHint")}</span>
                </>
              ) : null}
            </span>
          }
          action={
            <span className="sp-pv-row">
              <Button
                size="xs"
                variant="secondary"
                disabled={!pv.canBuild}
                onClick={pv.rebuild}
                data-testid="sp-pv-again"
              >
                {t("preview.failed.again")}
              </Button>
              {view.build ? (
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={onLog}
                  data-testid="sp-pv-open-log"
                >
                  <ScrollText size="0.6875rem" aria-hidden="true" />
                  {t("preview.failed.log")}
                </Button>
              ) : null}
            </span>
          }
        />
      );
    }
    case "cancelled":
      return (
        <p className="sp-pv-muted" data-testid="sp-pv-cancelled">
          {t("preview.cancelled")}
        </p>
      );
    case "quota":
      return (
        <Notice
          tone="warn"
          role="alert"
          text={
            <span data-testid="sp-pv-quota">
              {t("preview.quota", { limit: view.limit })}
            </span>
          }
        />
      );
    case "idle":
      return null;
  }
};

type PanelProps = {
  docId: string;
  /** Название документа для заголовка. */
  docName: string;
  /** Открытый файл документа: под страницей список замечаний к нему. `null`: список не нужен. */
  file?: string | null;
  /** Показать строку файла в редакторе (список замечаний). */
  onLine?: (line: number) => void;
};

/**
 * Предпросмотр PDF документа по условиям студента (pack-studio-ux.md, 5.4 и 5.5, срез S9): условия
 * те же, что на экране; сборка стартует сама при открытии; пример данных и вариант документа
 * выбираются тут же; под страницей замечания к файлу. Один и тот же в «Содержимом» и в
 * «Подробностях» «Результата». Пересоздавайте его на каждый документ (`key`).
 */
export const PreviewPanel = ({ docId, docName, file, onLine }: PanelProps) => {
  const { t, i18n } = useTranslation("packSpace");
  const { workspace } = useSpace();
  const pv = usePreviewBuild(docId);
  const ids = useId();
  const [log, setLog] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const lang = i18n.language;
  const { view } = pv;
  const hasBuild = view.kind === "ready" || view.kind === "failed";
  const stale = view.kind === "ready" && view.stale !== null;
  const buildId =
    view.kind === "ready" || view.kind === "failed"
      ? (view.build?.id ?? null)
      : null;
  return (
    <div className="sp-pv" data-testid="sp-preview" data-doc={docId}>
      <div className="sp-pv-top">
        <div className="sp-pv-head">
          <span className="sp-pv-kicker">{t("preview.title")}</span>
          <h3 className="sp-pv-title">{docName}</h3>
        </div>
        {view.kind === "ready" ? (
          <button
            type="button"
            className="icon-btn sm"
            aria-label={t("preview.full")}
            title={t("preview.full")}
            data-testid="sp-pv-full"
            onClick={() => {
              setFull(true);
            }}
          >
            <Maximize2 size="0.875rem" aria-hidden="true" />
          </button>
        ) : null}
      </div>

      <Conditions pv={pv} />

      <div className="sp-pv-fields">
        {pv.example.list.length > 1 ? (
          <div className="sp-pv-field">
            <label htmlFor={`${ids}-example`}>{t("preview.example")}</label>
            <Select
              id={`${ids}-example`}
              value={pv.example.id}
              ariaLabel={t("preview.example")}
              onValueChange={pv.example.set}
              options={pv.example.list.map((item) => ({
                value: item.id,
                label: item.label
                  ? pickLocalized(item.label, lang, item.id)
                  : item.id,
                isDisabled: item.error !== null,
              }))}
            />
            {pv.example.broken ? (
              <p className="sp-pv-hint" role="alert" data-testid="sp-pv-broken">
                {t("preview.exampleBroken", { reason: pv.example.broken })}
              </p>
            ) : null}
          </div>
        ) : null}
        {pv.variant ? (
          <div className="sp-pv-field">
            <label htmlFor={`${ids}-variant`}>{t("preview.variant")}</label>
            <Select
              id={`${ids}-variant`}
              value={pv.variant.id ?? ""}
              ariaLabel={t("preview.variant")}
              onValueChange={pv.variant.set}
              options={pv.variant.list.map((item) => ({
                value: item.id,
                label: pickLocalized(item.label, lang, item.id),
              }))}
            />
            {pv.variant.noPdf ? (
              <p className="sp-pv-hint" data-testid="sp-pv-variant-nopdf">
                {t("preview.variantNoPdf")}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      {view.kind !== "loading" &&
      view.kind !== "noPdf" &&
      view.kind !== "notInKit" &&
      view.kind !== "unavailable" ? (
        <div className="sp-pv-run">
          <Button
            size="sm"
            variant={stale || !hasBuild ? "primary" : "secondary"}
            disabled={!pv.canBuild}
            onClick={pv.rebuild}
            data-testid="sp-pv-build"
          >
            {pv.starting ? (
              <Spinner size="sm" />
            ) : hasBuild ? (
              <RotateCw size="0.75rem" aria-hidden="true" />
            ) : (
              <Play size="0.75rem" aria-hidden="true" />
            )}
            {hasBuild ? t("preview.rebuild") : t("preview.build")}
          </Button>
        </div>
      ) : null}

      <PreviewState
        pv={pv}
        onLog={() => {
          setLog(buildId);
        }}
        onFull={() => {
          setFull(true);
        }}
      />

      {file != null && onLine ? (
        <Findings workspaceId={workspace.id} path={file} onLine={onLine} />
      ) : null}

      <LogModal
        workspaceId={workspace.id}
        buildId={log}
        onClose={() => {
          setLog(null);
        }}
      />
      <PdfFullModal
        workspaceId={workspace.id}
        build={view.kind === "ready" ? view.build : undefined}
        isOpen={full}
        onClose={() => {
          setFull(false);
        }}
      />
    </div>
  );
};

export default PreviewPanel;
