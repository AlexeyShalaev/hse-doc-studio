import { useState } from "react";
import { FilePlus2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useWriteCi } from "@entities/git-remote";
import { getDocMeta, useDocuments } from "@entities/document";
import { describeGitError, useGitContents } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { Modal } from "@shared/ui/Modal";
import { Facts, ResultFrame } from "@shared/ui/ResultFrame";
import { Spinner } from "@shared/ui/Spinner";
import {
  DEFAULT_CI_OPTIONS,
  ciFileState,
  ciProblems,
  type CiOptions,
} from "../model/ciOptions";
import { useCiPreviewState } from "../model/useCiPreviewState";
import { useFocusFooter } from "../model/useFocusFooter";
import { CiOptionsPanel } from "./CiOptionsPanel";
import { DialogBody } from "./DialogBody";
import { CiPreviewPane } from "./CiPreviewPane";

export type CiGeneratorDialogProps = {
  isOpen: boolean;
  projectId: string;
  onClose: () => void;
};

// Автосборка: Студия готовит файл для GitHub Actions или GitLab CI, человек
// выбирает, что и когда собирать, смотрит файл и записывает его в проект.
// Файл попадёт в репозиторий при следующей синхронизации.
export const CiGeneratorDialog = ({
  isOpen,
  projectId,
  onClose,
}: CiGeneratorDialogProps) => {
  const { t, i18n } = useTranslation("gitExchange");
  const documents = useDocuments(projectId);
  const contents = useGitContents(projectId, isOpen);
  const writer = useWriteCi();

  const [options, setOptions] = useState<CiOptions>(DEFAULT_CI_OPTIONS);
  const [overwrite, setOverwrite] = useState(false);
  const [ndaAck, setNdaAck] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [written, setWritten] = useState<string[] | null>(null);

  const problems = ciProblems(options);
  const state = useCiPreviewState(
    projectId,
    options,
    isOpen && written === null,
  );
  const file = state.preview?.files[0] ?? null;
  const fileState = file ? ciFileState(file) : null;
  const hasNda = (contents.data?.nda_files ?? 0) > 0;
  const lang = i18n.language.startsWith("en") ? "en" : "ru";

  const choices = (documents.data ?? []).map((doc) => ({
    id: doc.id,
    label: getDocMeta(doc.id, doc, lang).name,
  }));

  const canWrite =
    !writer.isPending &&
    problems.length === 0 &&
    file !== null &&
    !state.isLoading &&
    state.error === null &&
    fileState !== "same" &&
    (fileState !== "differs" || overwrite) &&
    (!hasNda || ndaAck);

  const change = (next: CiOptions): void => {
    setOptions(next);
    // Подтверждения относятся к конкретному файлу: другой набор настроек их снимает.
    setOverwrite(false);
    setFailure(null);
  };

  const close = (): void => {
    if (writer.isPending) return;
    setOptions(DEFAULT_CI_OPTIONS);
    setOverwrite(false);
    setNdaAck(false);
    setFailure(null);
    setWritten(null);
    onClose();
  };

  const write = (): void => {
    if (!canWrite) return;
    setFailure(null);
    writer.mutate(
      { projectId, params: { ...state.request, overwrite } },
      {
        onSuccess: (result) => {
          setWritten(result.written);
        },
        onError: (error) => {
          setFailure(describeGitError(error, t("ci.writeFailed")));
        },
      },
    );
  };

  const done = written !== null;
  const footerRef = useFocusFooter(done ? "done" : "form");

  const body = done ? (
    <ResultFrame
      tone={written.length > 0 ? "ok" : "warn"}
      role="status"
      title={
        written.length > 0 ? t("ci.done.title") : t("ci.done.nothingTitle")
      }
      testId="ci-done"
      actions={
        <button
          type="button"
          className="btn"
          onClick={() => {
            setWritten(null);
          }}
        >
          {t("ci.done.again")}
        </button>
      }
    >
      <p style={{ margin: 0 }}>
        {written.length > 0 ? t("ci.done.text") : t("ci.done.nothingText")}
      </p>
      {written.length > 0 && (
        <Facts
          items={written.map((path): [string, string] => [
            t("ci.done.file"),
            path,
          ])}
        />
      )}
    </ResultFrame>
  ) : (
    <div
      className="flex"
      style={{ gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}
    >
      <div style={{ flex: "1 1 240px", minWidth: 0, maxWidth: 300 }}>
        <CiOptionsPanel
          options={options}
          onChange={change}
          documents={choices}
          documentsLoading={documents.isLoading}
          documentsFailed={documents.isError}
          problems={problems}
          disabled={writer.isPending}
        />
      </div>
      <div
        className="flex flex-col"
        style={{ flex: "2 1 360px", minWidth: 0, gap: 12 }}
      >
        <CiPreviewPane
          preview={state.preview}
          isLoading={state.isLoading}
          error={state.error}
          onRetry={state.retry}
          invalid={problems.length > 0}
          overwrite={overwrite}
          onOverwriteChange={setOverwrite}
          hasNda={hasNda}
          ndaAck={ndaAck}
          onNdaAckChange={setNdaAck}
          disabled={writer.isPending}
        />
        {failure !== null && <Notice tone="err" role="alert" text={failure} />}
      </div>
    </div>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={820}
      title={t("ci.title")}
      description={done ? undefined : t("ci.description")}
      footer={
        <div ref={footerRef} style={{ display: "contents" }}>
          {done ? (
            <button
              type="button"
              className="btn primary"
              autoFocus
              onClick={close}
            >
              {t("ci.done.close")}
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn"
                onClick={close}
                disabled={writer.isPending}
              >
                {t("ci.cancel")}
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={!canWrite}
                onClick={write}
              >
                {writer.isPending ? (
                  <Spinner size="sm" />
                ) : (
                  <FilePlus2 size={12} aria-hidden="true" />
                )}
                {t("ci.write")}
              </button>
            </>
          )}
        </div>
      }
    >
      <DialogBody>{body}</DialogBody>
    </Modal>
  );
};
