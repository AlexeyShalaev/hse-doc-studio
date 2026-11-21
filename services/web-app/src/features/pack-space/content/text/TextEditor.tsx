import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, FileText, Lock, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  isJinjaPath,
  languageForPackPath,
  lintTargetOf,
  packErrorText,
  packStudioKeys,
  usePackFile,
  usePackFilesRevision,
  usePackHints,
  usePackLint,
  versionDirOf,
  type PackEditorHints,
  type PackFile,
} from "@entities/pack-studio";
import {
  StaleFileBanner,
  findingsToDiagnostics,
  packCompletionExtension,
} from "@features/pack-file-editor";
import {
  Button,
  CodeEditor,
  ErrorState,
  Spinner,
  type RevealRequest,
} from "@shared/ui";
import { setContentDirty } from "../contentGuard";
import { onRevealLine, takePendingReveal } from "./revealLine";
import { pickFinding, suggestFix } from "./finding";
import { useAutosaveFile } from "./useAutosaveFile";
import "./space-content-text.css";

// Редактор «Текста» документа (pack-studio-ux.md, 5.5, срез S8b): текст пишется сам, рядом
// пометка «записано», под редактором ближайшее замечание и кнопка «Исправить», где оно есть.

const GUARD_OWNER = "segment-text-autosave";

// Текст файла, каким его впервые открыли за это посещение Студии: к нему ведёт «Вернуть как было».
const opened = new Map<string, string>();
const rememberOpened = (workspaceId: string, file: PackFile): string => {
  const key = `${workspaceId}\u0000${file.path}`;
  const known = opened.get(key);
  if (known !== undefined) return known;
  opened.set(key, file.content);
  return file.content;
};

export type TextEditorProps = {
  workspaceId: string;
  path: string;
  /** Выпущенная версия: правок нет, есть «Править копию». */
  readOnly: boolean;
  /** «Править копию» (главная кнопка пространства это срез S4; здесь переход по контракту каркаса). */
  onCopy: () => void;
};

const Loaded = ({
  workspaceId,
  file,
  readOnly,
  onCopy,
}: {
  workspaceId: string;
  file: PackFile;
  readOnly: boolean;
  onCopy: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const client = useQueryClient();
  const path = file.path;
  // Записи файлов пространства: проверки читаются заново после каждой (тот же ключ у списка
  // «Замечания к файлу» справа, поэтому запрос один).
  const revision = usePackFilesRevision(workspaceId);
  const autosave = useAutosaveFile(workspaceId, file);
  const versionDir = versionDirOf(path);
  const hints = usePackHints(workspaceId, versionDir);
  const lint = usePackLint(workspaceId, lintTargetOf(path), String(revision));
  const [caret, setCaret] = useState(1);
  const [reveal, setReveal] = useState<RevealRequest | undefined>(undefined);
  // «Строка N» из списка замечаний справа: прокрутить редактор к строке.
  useEffect(() => {
    const show = (request: { line: number; token: number }) => {
      setReveal({ line: request.line, token: request.token });
    };
    const waiting = takePendingReveal(path);
    if (waiting) show(waiting);
    return onRevealLine(path, show);
  }, [path]);
  const locked = readOnly || file.readOnly !== null;
  const language = languageForPackPath(path);
  const inVersionFiles = path.includes("/files/") && versionDir !== null;
  const original = useMemo(
    () => rememberOpened(workspaceId, file),
    [workspaceId, file],
  );

  const extensions = useMemo(
    () => [
      packCompletionExtension({
        getHints: () =>
          versionDir === null
            ? null
            : (client.getQueryData<PackEditorHints>(
                packStudioKeys.hints(workspaceId, versionDir),
              ) ?? null),
        jinja: inVersionFiles || isJinjaPath(path),
        macros: inVersionFiles && language === "latex",
      }),
    ],
    [client, workspaceId, versionDir, inVersionFiles, path, language],
  );
  const diagnostics = useMemo(
    () => findingsToDiagnostics(lint.data?.findings ?? [], path),
    [lint.data, path],
  );

  const finding = pickFinding(lint.data?.findings, path, caret);
  const others = Math.max(
    0,
    (lint.data?.findings ?? []).filter((item) => item.path === path).length - 1,
  );
  const fix = useMemo(
    () =>
      finding && !locked
        ? suggestFix(
            finding,
            autosave.text,
            (hints.data?.meta_fields ?? []).map((field) => field.key),
          )
        : null,
    [finding, locked, autosave.text, hints.data],
  );
  const line = finding?.line ?? fix?.line ?? null;

  // Правка, которая не ушла на диск (конфликт, сбой), не должна пропасть при уходе с экрана.
  const stuck = autosave.conflict !== null || autosave.status === "failed";
  useEffect(() => {
    setContentDirty(GUARD_OWNER, stuck);
    return () => {
      setContentDirty(GUARD_OWNER, false);
    };
  }, [stuck]);
  const pending = autosave.dirty || autosave.status === "saving";
  useEffect(() => {
    if (!pending) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
    };
  }, [pending]);

  const revert = () => {
    if (!window.confirm(t("content.text.revertAsk"))) return;
    autosave.edit(original);
    autosave.flush();
  };

  return (
    <div className="sp-ct-text-box" data-testid="ct-text">
      <div className="sp-ct-editor">
        <div className="sp-ct-text-head">
          <FileText size="0.875rem" aria-hidden="true" />
          <b className="sp-ct-text-name" title={path}>
            {path.split("/").pop()}
          </b>
          {!locked &&
            (autosave.status === "waiting" || autosave.status === "saving") && (
              <span className="sp-ct-text-state" data-testid="ct-text-state">
                <Spinner size="sm" />
                {t("content.text.saving")}
              </span>
            )}
          {!locked && autosave.status === "saved" && (
            <span
              className="sp-ct-text-state ok"
              data-testid="ct-text-state"
              role="status"
            >
              <Check size="0.6875rem" aria-hidden="true" />
              {t("content.text.saved")}
            </span>
          )}
          {locked && (
            <span
              className="sp-ct-text-state"
              title={t("content.released.readOnly")}
              aria-label={t("content.released.readOnly")}
              data-testid="ct-text-lock"
            >
              <Lock size="0.6875rem" aria-hidden="true" />
            </span>
          )}
          {!locked && autosave.text !== original && (
            <Button
              size="xs"
              variant="ghost"
              onClick={revert}
              data-testid="ct-text-revert"
            >
              <RotateCcw size="0.6875rem" aria-hidden="true" />
              {t("content.text.revert")}
            </Button>
          )}
          {readOnly && (
            <Button
              size="xs"
              variant="secondary"
              onClick={onCopy}
              data-testid="ct-text-copy"
            >
              {t("content.text.copy")}
            </Button>
          )}
        </div>
        <div className="sp-ct-text-code" data-testid="pack-code-editor">
          <CodeEditor
            value={autosave.text}
            onChange={autosave.edit}
            onSave={autosave.flush}
            onStats={(stats) => {
              setCaret(stats.line);
            }}
            readOnly={locked}
            language={language}
            diagnostics={diagnostics}
            {...(reveal ? { reveal } : {})}
            extraExtensions={extensions}
            ariaLabel={t("content.text.label")}
          />
        </div>
      </div>
      {autosave.conflict && (
        <StaleFileBanner
          diskContent={autosave.conflict.diskContent}
          getBuffer={() => autosave.text}
          busy={autosave.status === "saving"}
          onTakeDisk={autosave.takeDisk}
          onKeepMine={autosave.keepMine}
        />
      )}
      {autosave.status === "failed" && (
        <div
          className="sp-ct-banner sp-ct-text-err"
          role="alert"
          data-testid="ct-text-failed"
        >
          <CircleAlert size="0.875rem" aria-hidden="true" />
          <div className="sp-ct-text-msg">
            <b>{t("content.text.failed")}</b>{" "}
            <span>{packErrorText(autosave.error)}</span>
          </div>
          <Button size="xs" variant="secondary" onClick={autosave.flush}>
            {t("content.text.retry")}
          </Button>
        </div>
      )}
      {finding && (
        <div
          className={`sp-ct-banner sp-ct-text-${finding.severity}`}
          role="status"
          data-testid="ct-text-finding"
        >
          <CircleAlert size="0.875rem" aria-hidden="true" />
          <div className="sp-ct-text-msg">
            {line !== null ? (
              <button
                type="button"
                className="sp-ct-text-line"
                onClick={() => {
                  setReveal((prev) => ({
                    line,
                    token: (prev?.token ?? 0) + 1,
                  }));
                }}
              >
                {t("content.text.line", { line })}:
              </button>
            ) : null}{" "}
            <span>
              {fix
                ? t("content.text.typo", { wrong: fix.wrong, right: fix.right })
                : finding.message}
            </span>
            {others > 0 && (
              <span className="sp-ct-text-more">
                {" "}
                {t("content.text.others", { count: others })}
              </span>
            )}
          </div>
          {fix && (
            <Button
              size="xs"
              variant="secondary"
              onClick={() => {
                autosave.edit(fix.apply(autosave.text));
              }}
              data-testid="ct-text-fix"
            >
              {t("content.text.fix")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

/** Файл целиком: загрузка, сбой чтения и редактор. Пересоздаётся на каждый файл (`key`). */
export const TextEditor = ({
  workspaceId,
  path,
  readOnly,
  onCopy,
}: TextEditorProps) => {
  const file = usePackFile(workspaceId, path);
  if (file.isPending) {
    return (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner size="md" />
      </div>
    );
  }
  if (file.isError) {
    return (
      <ErrorState
        description={packErrorText(file.error)}
        onRetry={() => void file.refetch()}
      />
    );
  }
  return (
    <Loaded
      key={path}
      workspaceId={workspaceId}
      file={file.data}
      readOnly={readOnly}
      onCopy={onCopy}
    />
  );
};
