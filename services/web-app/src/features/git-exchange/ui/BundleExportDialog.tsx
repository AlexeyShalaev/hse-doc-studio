import { useId, useState, type FormEvent } from "react";
import { Download, Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  describeGitError,
  useExportBundle,
  useGitContents,
  type ExportBundleResult,
} from "@entities/git-sync";
import { downloadBlob, flushPendingSaves, formatFileSize } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { Modal } from "@shared/ui/Modal";
import { Facts, ResultFrame } from "@shared/ui/ResultFrame";
import { Spinner } from "@shared/ui/Spinner";
import { useFocusFooter } from "../model/useFocusFooter";
import { CheckRow } from "./CheckRow";
import { DialogBody } from "./DialogBody";
import { PasswordField } from "./PasswordField";

export type BundleExportDialogProps = {
  isOpen: boolean;
  projectId: string;
  onClose: () => void;
};

// Выгрузка проекта в один файл с историей версий. Файл можно защитить паролем;
// пароль Студия не хранит, поэтому окно просит повторить его, чтобы опечатка не
// сделала файл нечитаемым. Сохранённый файл остаётся в окне: его можно скачать ещё раз.
export const BundleExportDialog = ({
  isOpen,
  projectId,
  onClose,
}: BundleExportDialogProps) => {
  const { t } = useTranslation("gitExchange");
  const formId = useId();
  const contents = useGitContents(projectId, isOpen);
  const exporter = useExportBundle();

  const [protect, setProtect] = useState(false);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState<
    (ExportBundleResult & { protected: boolean }) | null
  >(null);
  const [working, setWorking] = useState(false);
  const footerRef = useFocusFooter(saved ? "done" : "form");

  const mismatch = protect && repeat !== "" && repeat !== password;
  const canExport =
    !working && (!protect || (password !== "" && password === repeat));
  const ndaFiles = contents.data?.nda_files ?? 0;

  const close = (): void => {
    if (working) return;
    setProtect(false);
    setPassword("");
    setRepeat("");
    setFailure(null);
    setSaved(null);
    onClose();
  };

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!canExport) return;
    setFailure(null);
    setWorking(true);
    try {
      // Правки в редакторах дописываются с задержкой: без них файл вышел бы старее экрана.
      const flushed = await flushPendingSaves();
      if (flushed.failed > 0) {
        setFailure(t("export.saveFailed"));
        return;
      }
      const exported = await exporter.mutateAsync({
        projectId,
        ...(protect ? { password } : {}),
      });
      downloadBlob(exported.blob, exported.filename);
      setSaved({ ...exported, protected: protect });
      setPassword("");
      setRepeat("");
    } catch (error) {
      setFailure(describeGitError(error, t("export.failed")));
    } finally {
      setWorking(false);
    }
  };

  const form = (
    <form
      id={formId}
      onSubmit={(event) => {
        void submit(event);
      }}
      noValidate
      className="flex flex-col"
      style={{ gap: 14 }}
    >
      <p
        className="dim"
        style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55 }}
      >
        {t("export.explain")}
      </p>

      {contents.isLoading && (
        <div
          className="flex items-center dim"
          style={{ gap: 8, fontSize: 12 }}
          role="status"
        >
          <Spinner size="sm" />
          {t("export.loading")}
        </div>
      )}
      {contents.data && (
        <Facts
          items={[
            [t("export.commits"), String(contents.data.commits)],
            [t("export.files"), String(contents.data.files)],
            [t("export.size"), formatFileSize(contents.data.bytes)],
          ]}
        />
      )}

      <div className="flex flex-col" style={{ gap: 10 }}>
        <CheckRow
          checked={protect}
          disabled={working}
          onChange={(next) => {
            setProtect(next);
            setFailure(null);
          }}
          hint={t("export.protectHint")}
          testId="export-protect"
        >
          <span
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <Lock size={12} aria-hidden="true" />
            {t("export.protect")}
          </span>
        </CheckRow>
        {protect && (
          <div className="flex flex-col" style={{ gap: 10 }}>
            <PasswordField
              label={t("export.password")}
              value={password}
              disabled={working}
              onChange={setPassword}
              autoFocus
              testId="export-password"
            />
            <PasswordField
              label={t("export.repeat")}
              value={repeat}
              disabled={working}
              onChange={setRepeat}
              error={mismatch ? t("export.mismatch") : null}
              hint={t("export.passwordHint")}
              testId="export-repeat"
            />
          </div>
        )}
      </div>

      {ndaFiles > 0 && !protect && (
        <Notice
          tone="warn"
          role="status"
          text={t("export.nda")}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                setProtect(true);
              }}
            >
              {t("export.ndaProtect")}
            </button>
          }
        />
      )}
      {failure !== null && <Notice tone="err" role="alert" text={failure} />}
    </form>
  );

  const done = saved && (
    <ResultFrame
      tone="ok"
      role="status"
      title={t("export.done.title")}
      testId="export-done"
      actions={
        <button
          type="button"
          className="btn"
          onClick={() => {
            downloadBlob(saved.blob, saved.filename);
          }}
        >
          <Download size={12} aria-hidden="true" />
          {t("export.done.again")}
        </button>
      }
    >
      <p style={{ margin: 0 }}>{t("export.done.text")}</p>
      <Facts
        items={[
          [t("export.done.file"), saved.filename],
          [t("export.done.size"), formatFileSize(saved.blob.size)],
          [
            t("export.done.protection"),
            saved.protected
              ? t("export.done.protected")
              : t("export.done.open"),
          ],
        ]}
      />
      {saved.protected && (
        <Notice tone="info" text={t("export.done.passwordNote")} />
      )}
    </ResultFrame>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={520}
      title={t("export.title")}
      description={saved ? undefined : t("export.description")}
      footer={
        <div ref={footerRef} style={{ display: "contents" }}>
          {saved ? (
            <button
              type="button"
              className="btn primary"
              autoFocus
              onClick={close}
            >
              {t("export.done.close")}
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn"
                onClick={close}
                disabled={working}
              >
                {t("export.cancel")}
              </button>
              <button
                type="submit"
                form={formId}
                className="btn primary"
                disabled={!canExport}
              >
                {working ? (
                  <Spinner size="sm" />
                ) : (
                  <Download size={12} aria-hidden="true" />
                )}
                {working ? t("export.working") : t("export.submit")}
              </button>
            </>
          )}
        </div>
      }
    >
      <DialogBody>{done ?? form}</DialogBody>
    </Modal>
  );
};
