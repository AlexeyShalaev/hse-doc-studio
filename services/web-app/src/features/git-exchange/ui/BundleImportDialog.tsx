import { useId, useRef, useState, type FormEvent } from "react";
import { Upload } from "lucide-react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { AUTHOR_PROFILE_PATH, gitConflictsPath } from "@entities/git-sync";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { FileDropZone, type FileDropZoneHandle } from "@shared/ui/FileDropZone";
import { Spinner } from "@shared/ui/Spinner";
import {
  BUNDLE_ACCEPT,
  isBundleName,
  isEncryptedBundleName,
} from "../lib/bundleNames";
import { bundleFailureTarget } from "../model/bundleFailure";
import { useBundleFailureText } from "../model/useBundleFailureText";
import { useBundleImport } from "../model/useBundleImport";
import { useFocusFooter } from "../model/useFocusFooter";
import { BundleFileCard } from "./BundleFileCard";
import { DialogBody } from "./DialogBody";
import { ImportProgress } from "./ImportProgress";
import { ImportResult } from "./ImportResult";
import { PasswordField } from "./PasswordField";

export type BundleImportDialogProps = {
  isOpen: boolean;
  projectId: string;
  onClose: () => void;
  /** Почему импорт сейчас невозможен (проект только для чтения); null, если можно. */
  disabledReason?: string | null;
};

// Импорт файла от коллеги: выбрать или перетащить файл, при необходимости ввести
// пароль, дождаться слияния. Если у обоих изменены одни и те же места, окно
// передаёт человека на экран конфликтов. Пока файл едет или сливается, окно не
// закрывается: операция идёт на сервере, а итог показывает только оно.
export const BundleImportDialog = ({
  isOpen,
  projectId,
  onClose,
  disabledReason = null,
}: BundleImportDialogProps) => {
  const { t } = useTranslation("gitExchange");
  const navigate = useNavigate();
  const formId = useId();
  const zoneRef = useRef<FileDropZoneHandle>(null);
  const failureText = useBundleFailureText();
  const flow = useBundleImport(projectId);
  const footerRef = useFocusFooter(flow.stage);

  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [wrongKind, setWrongKind] = useState(false);
  // Сервер сказал, что пароль нужен: поле остаётся, пока не выбран другой файл.
  const [serverWantsPassword, setServerWantsPassword] = useState(false);

  const { stage, failure, result } = flow;
  const busy = stage === "uploading" || stage === "running";
  const target = failure ? bundleFailureTarget(failure.code) : null;
  const encrypted = file !== null && isEncryptedBundleName(file.name);
  // Пароль просят и у файла без «.hseenc» в имени, если сервер сказал, что он нужен.
  if (target === "password" && !serverWantsPassword) {
    setServerWantsPassword(true);
  }
  const needsPassword = encrypted || serverWantsPassword;
  const canImport =
    file !== null &&
    disabledReason === null &&
    (!needsPassword || password !== "");

  const close = (): void => {
    if (busy) return;
    flow.reset();
    setFile(null);
    setPassword("");
    setWrongKind(false);
    setServerWantsPassword(false);
    onClose();
  };

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (!file || !canImport || busy) return;
    void flow.start(file, needsPassword ? password : "");
  };

  const pick = (picked: File | null): void => {
    setWrongKind(false);
    setFile(picked);
    setPassword("");
    setServerWantsPassword(false);
    flow.dismissFailure();
  };

  const openConflicts = (): void => {
    close();
    void navigate(gitConflictsPath(projectId));
  };

  const failureNotice = (() => {
    if (!failure || target === "password") return null;
    const { message, hint } = failureText(failure);
    const text = (
      <>
        <strong style={{ fontWeight: 600 }}>{message}</strong>
        {hint && <span style={{ display: "block" }}>{hint}</span>}
      </>
    );
    return (
      <Notice
        tone="err"
        role="alert"
        text={text}
        {...(target === "profile"
          ? {
              action: (
                <button
                  type="button"
                  className="btn xs"
                  onClick={() => {
                    close();
                    void navigate(AUTHOR_PROFILE_PATH);
                  }}
                >
                  {t("import.openProfile")}
                </button>
              ),
            }
          : {})}
      />
    );
  })();

  const passwordError =
    failure && target === "password" ? failureText(failure).message : null;

  // --- содержимое по шагам --------------------------------------------------------

  const choose = (
    <form
      id={formId}
      onSubmit={submit}
      noValidate
      className="flex flex-col"
      style={{ gap: 14 }}
    >
      {disabledReason !== null && (
        <Notice tone="warn" role="status" text={disabledReason} />
      )}
      <FileDropZone
        ref={zoneRef}
        showZone={file === null}
        accept={BUNDLE_ACCEPT}
        isAcceptable={(picked) => isBundleName(picked.name)}
        onFile={pick}
        onReject={() => {
          setWrongKind(true);
        }}
        disabled={disabledReason !== null}
        title={t("import.drop")}
        action={t("import.choose")}
        activeTitle={t("import.dropActive")}
        hint={t("import.accept")}
        inputLabel={t("import.title")}
        testId="import-dropzone"
        inputTestId="import-input"
      />
      {file !== null && (
        <BundleFileCard
          file={file}
          editable
          onReplace={() => {
            zoneRef.current?.open();
          }}
          onRemove={() => {
            pick(null);
          }}
        />
      )}
      {wrongKind && (
        <Notice tone="err" role="alert" text={t("import.wrongKind")} />
      )}
      {needsPassword && file !== null && (
        <PasswordField
          label={t("import.password")}
          value={password}
          onChange={(value) => {
            setPassword(value);
            flow.dismissFailure();
          }}
          hint={t("import.passwordHint")}
          error={passwordError}
          autoFocus
          testId="import-password"
        />
      )}
      {failureNotice}
      {flow.cancelled && (
        <Notice tone="info" role="status" text={t("import.cancelled")} />
      )}
      {file === null && !failure && !flow.cancelled && (
        <p
          className="dim"
          style={{ margin: 0, fontSize: 12, lineHeight: 1.55 }}
        >
          {t("import.explain")}
        </p>
      )}
    </form>
  );

  const body = (() => {
    if (stage === "uploading") {
      return (
        <div className="flex flex-col" style={{ gap: 14 }}>
          {file !== null && (
            <BundleFileCard
              file={file}
              editable={false}
              onReplace={() => undefined}
              onRemove={() => undefined}
            />
          )}
          <ImportProgress kind="upload" percent={flow.percent} />
        </div>
      );
    }
    if (stage === "running") {
      return (
        <div className="flex flex-col" style={{ gap: 14 }}>
          <p
            className="dim"
            style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}
          >
            {t("import.progress.lead")}
          </p>
          <ImportProgress kind="merge" operation={flow.operation} />
          {flow.lost && (
            <Notice
              tone="warn"
              role="alert"
              text={t("import.lost")}
              action={
                <button
                  type="button"
                  className="btn xs"
                  onClick={flow.retryLookup}
                >
                  {t("import.lostRetry")}
                </button>
              }
            />
          )}
        </div>
      );
    }
    if (stage === "done" && result) return <ImportResult result={result} />;
    return choose;
  })();

  const conflicts = stage === "done" && result?.outcome === "conflicts";

  const footer = (() => {
    if (stage === "uploading") {
      return (
        <button type="button" className="btn" onClick={flow.cancel}>
          {t("import.progress.cancelUpload")}
        </button>
      );
    }
    if (stage === "running") {
      return (
        <button
          type="button"
          className="btn"
          disabled={!flow.operation?.cancellable || flow.isCancelling}
          onClick={flow.cancel}
        >
          {flow.isCancelling && <Spinner size="sm" />}
          {flow.isCancelling
            ? t("import.progress.cancelling")
            : t("import.progress.cancel")}
        </button>
      );
    }
    if (stage === "done") {
      return conflicts ? (
        <>
          <button type="button" className="btn" onClick={close}>
            {t("import.later")}
          </button>
          <button
            type="button"
            className="btn primary"
            autoFocus
            onClick={openConflicts}
          >
            {t("import.openConflicts")}
          </button>
        </>
      ) : (
        <button type="button" className="btn primary" autoFocus onClick={close}>
          {t("import.done")}
        </button>
      );
    }
    return (
      <>
        <button type="button" className="btn" onClick={close}>
          {t("import.cancel")}
        </button>
        <button
          type="submit"
          form={formId}
          className="btn primary"
          disabled={!canImport}
        >
          <Upload size={12} aria-hidden="true" />
          {t("import.submit")}
        </button>
      </>
    );
  })();

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={560}
      title={t("import.title")}
      description={t("import.description")}
      footer={
        <div ref={footerRef} style={{ display: "contents" }}>
          {footer}
        </div>
      }
    >
      <DialogBody>{body}</DialogBody>
    </Modal>
  );
};
