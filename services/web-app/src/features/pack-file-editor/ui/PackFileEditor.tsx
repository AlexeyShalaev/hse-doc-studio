import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, ListChecks, RotateCcw, Save } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import {
  PackStaleFileError,
  isJinjaPath,
  isTextPath,
  languageForPackPath,
  lintTargetOf,
  packErrorText,
  packStudioApi,
  packStudioKeys,
  usePackFile,
  usePackHints,
  usePackLint,
  versionDirOf,
  type LintFailure,
  type PackEditorHints,
  type PackFile,
} from "@entities/pack-studio";
import { useIsPhoneWidth } from "@shared/lib";
import {
  Button,
  CodeEditor,
  EmptyState,
  ErrorState,
  Spinner,
  type RevealRequest,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { findingsToDiagnostics } from "../lib/findings";
import { packCompletionExtension } from "../lib/packCompletion";
import { GateFindings } from "./GateFindings";
import { ProblemsPanel } from "./ProblemsPanel";
import { StaleFileBanner } from "./StaleFileBanner";

export type PackFileEditorProps = {
  workspaceId: string;
  path: string;
  /** Меняется после каждой записи в пространстве: проверки версии перезапускаются. */
  lintEpoch: number;
  onSaved: () => void;
  onOpenFile: (path: string, line: number | null) => void;
  /** Перейти к строке открытого файла (из «Проблем» или по ссылке). */
  reveal?: RevealRequest | undefined;
  onDirtyChange?: ((dirty: boolean) => void) | undefined;
  /** Дополнительные кнопки в строке редактора (git рабочего пространства живёт в своей панели). */
  actions?: ReactNode;
  /** Вкладка предпросмотра (срез T7: сборка на тестовых данных); без неё стоит заглушка. */
  preview?: ReactNode;
  /** Находки проверки пака перед отправкой (lint_failed): сверху «Проблем». */
  gate?: LintFailure | null | undefined;
  onDismissGate?: (() => void) | undefined;
  /** Меняется, когда «Проблемы» нужно показать (пришли находки перед отправкой). */
  problemsFocus?: number | undefined;
};

type SidePane = "problems" | "preview";

/** Манифесты, у которых будет форма поверх YAML (5.0): пока открыт только «Исходник». */
const hasForm = (path: string): boolean =>
  /(^|\/)(pack|template|version|doc)\.yaml$/i.test(path) ||
  /\/checks\/[^/]+\.ya?ml$/i.test(path);

type LoadedProps = {
  workspaceId: string;
  file: PackFile;
  diagnostics: ReturnType<typeof findingsToDiagnostics>;
  reveal: RevealRequest | undefined;
  onSaved: () => void;
  onDirtyChange: ((dirty: boolean) => void) | undefined;
  actions: ReactNode;
};

type Conflict = { diskContent: string | null; diskEtag: string | null };

const LoadedEditor = ({
  workspaceId,
  file,
  diagnostics,
  reveal,
  onSaved,
  onDirtyChange,
  actions,
}: LoadedProps) => {
  const { t } = useTranslation("packStudio");
  const client = useQueryClient();
  const [value, setValue] = useState(file.content);
  const valueRef = useRef(file.content);
  const [saved, setSaved] = useState({
    content: file.content,
    etag: file.etag,
  });
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [savedOnce, setSavedOnce] = useState(false);
  const readOnly = file.readOnly !== null;
  const dirty = value !== saved.content;

  const versionDir = versionDirOf(file.path);
  const inVersionFiles = file.path.includes("/files/") && versionDir !== null;
  const language = languageForPackPath(file.path);
  // Расширения редактора создаются один раз на файл (редактор пересоздаётся по ключу).
  const extensions = useMemo(
    () => [
      packCompletionExtension({
        // Подсказки читаются из кэша запросов при каждом вызове: они приходят позже редактора.
        getHints: () =>
          versionDir === null
            ? null
            : (client.getQueryData<PackEditorHints>(
                packStudioKeys.hints(workspaceId, versionDir),
              ) ?? null),
        jinja: inVersionFiles || isJinjaPath(file.path),
        macros: inVersionFiles && language === "latex",
      }),
    ],
    [client, workspaceId, versionDir, inVersionFiles, file.path, language],
  );

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  // Несохранённая правка не уходит молча при закрытии вкладки.
  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
    };
  }, [dirty]);

  const write = useMutation({
    mutationFn: ({ text, ifMatch }: { text: string; ifMatch: string | null }) =>
      packStudioApi.writeFile(workspaceId, file.path, text, ifMatch),
    onSuccess: (version, { text }) => {
      setSaved({ content: text, etag: version.etag });
      setConflict(null);
      setSavedOnce(true);
      client.setQueryData(packStudioKeys.file(workspaceId, file.path), {
        ...file,
        content: text,
        etag: version.etag,
      });
      if (
        versionDir &&
        (isJinjaPath(file.path) || /version\.yaml$/i.test(file.path))
      ) {
        void client.invalidateQueries({
          queryKey: packStudioKeys.hints(workspaceId, versionDir),
        });
      }
      onSaved();
    },
    onError: (error) => {
      if (error instanceof PackStaleFileError) {
        setConflict({
          diskContent: error.diskContent,
          diskEtag: error.diskEtag,
        });
      }
    },
  });

  const save = useCallback(
    (text: string) => {
      if (readOnly || conflict || write.isPending) return;
      write.mutate({ text, ifMatch: saved.etag });
    },
    [readOnly, conflict, write, saved.etag],
  );

  const status = write.isPending
    ? t("editor.saving")
    : dirty
      ? t("editor.unsaved")
      : savedOnce
        ? t("editor.saved")
        : null;

  return (
    <div className="ps-editor-main">
      <div className="ps-editor-toolbar">
        <span className="ps-editor-file mono truncate" title={file.path}>
          {file.path.split("/").pop()}
          {dirty && (
            <span className="ps-dirty" aria-label={t("editor.unsaved")}>
              ●
            </span>
          )}
        </span>
        {status && (
          <span className="ps-editor-status" data-testid="editor-status">
            {status}
          </span>
        )}
        <span className="ps-editor-actions">
          {!readOnly && (
            <>
              <Button
                size="xs"
                variant="ghost"
                disabled={!dirty || write.isPending}
                onClick={() => {
                  valueRef.current = saved.content;
                  setValue(saved.content);
                }}
                title={t("editor.revert")}
              >
                <RotateCcw size="0.6875rem" />
                <span className="ps-hide-phone">{t("editor.revert")}</span>
              </Button>
              <Button
                size="xs"
                disabled={!dirty || write.isPending || conflict !== null}
                onClick={() => {
                  save(valueRef.current);
                }}
                data-testid="editor-save"
              >
                {write.isPending ? (
                  <Spinner size="sm" />
                ) : (
                  <Save size="0.6875rem" />
                )}
                {t("editor.save")}
              </Button>
            </>
          )}
          {actions}
        </span>
      </div>
      {readOnly && (
        <Notice
          tone="info"
          role="status"
          text={
            file.readOnly === "version_released"
              ? t("editor.readOnlyReleased")
              : t("editor.readOnlyRegistry")
          }
        />
      )}
      {conflict && (
        <StaleFileBanner
          diskContent={conflict.diskContent}
          getBuffer={() => valueRef.current}
          busy={write.isPending}
          onTakeDisk={() => {
            const disk = conflict.diskContent ?? "";
            valueRef.current = disk;
            setValue(disk);
            setSaved({ content: disk, etag: conflict.diskEtag });
            setConflict(null);
          }}
          onKeepMine={() => {
            write.mutate({
              text: valueRef.current,
              ifMatch: conflict.diskEtag,
            });
          }}
        />
      )}
      {write.isError && !(write.error instanceof PackStaleFileError) && (
        <Notice tone="err" role="alert" text={packErrorText(write.error)} />
      )}
      <div className="ps-editor-code" data-testid="pack-code-editor">
        <CodeEditor
          value={value}
          onChange={(next) => {
            valueRef.current = next;
            setValue(next);
          }}
          onSave={save}
          readOnly={readOnly}
          language={language}
          diagnostics={diagnostics}
          {...(reveal ? { reveal } : {})}
          extraExtensions={extensions}
          ariaLabel={file.path}
        />
      </div>
    </div>
  );
};

/** Вкладка предпросмотра без содержимого: страница его не передала. */
const PreviewPlaceholder = () => {
  const { t } = useTranslation("packStudio");
  return (
    <EmptyState
      compact
      icon={<Eye size="1.25rem" />}
      title={t("preview.title")}
      description={t("preview.soon")}
      testId="preview-placeholder"
    />
  );
};

/**
 * Редактор файла пака (template-studio.md, 5.0 и 5.4): вкладка «Исходник» с
 * редактором кода Студии, автодополнением Jinja и макросов \hse..., находками
 * линтера и схем в строке и панелью «Проблемы» справа (на телефоне под редактором).
 * Запись с If-Match; конфликт с чужой правкой разбирается баннером, ничего не теряя.
 */
export const PackFileEditor = ({
  workspaceId,
  path,
  lintEpoch,
  onSaved,
  onOpenFile,
  reveal,
  onDirtyChange,
  actions,
  preview,
  gate,
  onDismissGate,
  problemsFocus,
}: PackFileEditorProps) => {
  const { t } = useTranslation("packStudio");
  const phone = useIsPhoneWidth();
  const text = isTextPath(path);
  const file = usePackFile(workspaceId, text ? path : null);
  const target = lintTargetOf(path);
  const lint = usePackLint(workspaceId, target, String(lintEpoch));
  const versionDir = versionDirOf(path);
  // Подсказки автодополнения: редактор читает их из кэша запросов.
  usePackHints(workspaceId, versionDir);
  const [pane, setPane] = useState<SidePane>("problems");
  // Пришли находки перед отправкой: «Проблемы» выходят вперёд (состояние от пропа без эффекта).
  const [seenFocus, setSeenFocus] = useState(problemsFocus);
  if (problemsFocus !== seenFocus) {
    setSeenFocus(problemsFocus);
    if (pane !== "problems") setPane("problems");
  }
  const findings = lint.data?.findings;
  const diagnostics = useMemo(
    () => findingsToDiagnostics(findings ?? [], path),
    [findings, path],
  );

  let main: ReactNode;
  if (!text) {
    main = (
      <EmptyState
        compact
        title={t("editor.binaryTitle")}
        description={t("editor.binaryLead")}
      />
    );
  } else if (file.isPending) {
    main = (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner size="md" />
      </div>
    );
  } else if (file.isError) {
    main = (
      <ErrorState
        description={packErrorText(file.error)}
        onRetry={() => void file.refetch()}
      />
    );
  } else {
    main = (
      <LoadedEditor
        key={path}
        workspaceId={workspaceId}
        file={file.data}
        diagnostics={diagnostics}
        reveal={reveal}
        onSaved={onSaved}
        onDirtyChange={onDirtyChange}
        actions={actions}
      />
    );
  }

  const problemCount = (lint.data?.errors ?? 0) + (lint.data?.warnings ?? 0);

  return (
    <div
      className={clsx("ps-editor", phone && "ps-editor-phone")}
      data-testid="pack-file-editor"
    >
      <div className="ps-editor-center">
        {hasForm(path) && (
          <div
            className="ps-view-tabs"
            role="tablist"
            aria-label={t("editor.views")}
          >
            <button
              type="button"
              role="tab"
              aria-selected
              className="ps-view-tab active"
            >
              {t("editor.source")}
            </button>
            {/* Формы поверх YAML: срезы T11–T14. */}
            <button
              type="button"
              role="tab"
              aria-selected={false}
              className="ps-view-tab"
              disabled
              title={t("editor.formSoon")}
            >
              {t("editor.form")}
            </button>
          </div>
        )}
        {main}
      </div>
      <aside className="ps-side" aria-label={t("problems.title")}>
        <div className="ps-view-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={pane === "problems"}
            className={clsx("ps-view-tab", pane === "problems" && "active")}
            onClick={() => {
              setPane("problems");
            }}
            data-testid="side-tab-problems"
          >
            <ListChecks size="0.75rem" aria-hidden="true" />
            {t("problems.title")}
            {problemCount + (gate?.findings.length ?? 0) > 0 && (
              <span className="ps-count">
                {problemCount + (gate?.findings.length ?? 0)}
              </span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={pane === "preview"}
            className={clsx("ps-view-tab", pane === "preview" && "active")}
            onClick={() => {
              setPane("preview");
            }}
            data-testid="side-tab-preview"
          >
            <Eye size="0.75rem" aria-hidden="true" />
            {t("preview.title")}
          </button>
        </div>
        {pane === "problems" && gate && (
          <GateFindings
            failure={gate}
            onOpen={onOpenFile}
            onDismiss={() => {
              onDismissGate?.();
            }}
          />
        )}
        {pane === "problems" ? (
          target === null ? (
            <p className="ps-pane-empty" data-testid="problems-none">
              {t("problems.scopeNone")}
            </p>
          ) : (
            <ProblemsPanel
              path={path}
              lint={lint.data}
              loading={lint.isFetching}
              error={lint.error}
              onRecheck={() => void lint.refetch()}
              onOpen={onOpenFile}
            />
          )
        ) : (
          (preview ?? <PreviewPlaceholder />)
        )}
      </aside>
    </div>
  );
};
