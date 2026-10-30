import { useId, useState, type FormEvent } from "react";
import { Upload } from "lucide-react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Modal } from "@shared/ui/Modal";
import { Spinner } from "@shared/ui/Spinner";
import { useProjectImport } from "../model/useProjectImport";
import { ProjectImportView } from "./ProjectImportView";

export type ProjectImportDialogProps = {
  isOpen: boolean;
  onClose: () => void;
};

// Импорт проекта из локальной Студии: выбрать zip, дождаться загрузки и распаковки на сервере.
// Пока архив едет, окно можно только прервать; пока сервер распаковывает, оно не закрывается:
// итог (id нового проекта) показывает только оно.
export const ProjectImportDialog = ({
  isOpen,
  onClose,
}: ProjectImportDialogProps) => {
  const { t } = useTranslation("projectImport");
  const navigate = useNavigate();
  const formId = useId();
  const flow = useProjectImport();
  const [file, setFile] = useState<File | null>(null);

  const { stage, percent, result, failure } = flow;
  const unpacking = stage === "uploading" && percent >= 100;

  const close = (): void => {
    if (stage === "uploading") return;
    flow.reset();
    setFile(null);
    onClose();
  };

  const pick = (picked: File | null): void => {
    setFile(picked);
    if (stage === "failed") flow.reset();
  };

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (file && stage !== "uploading") void flow.start(file);
  };

  const open = (): void => {
    if (!result) return;
    const id = result.project_id;
    close();
    void navigate(`/projects/${id}/documents`);
  };

  const footer = (() => {
    if (stage === "uploading") {
      return (
        <button
          type="button"
          className="btn"
          onClick={flow.cancel}
          disabled={unpacking}
        >
          {unpacking && <Spinner size="sm" />}
          {t("uploading.cancel")}
        </button>
      );
    }
    if (stage === "done") {
      return (
        <>
          <button type="button" className="btn" onClick={close}>
            {t("done.later")}
          </button>
          <button
            type="button"
            className="btn primary"
            autoFocus
            onClick={open}
          >
            {t("done.open")}
          </button>
        </>
      );
    }
    return (
      <>
        <button type="button" className="btn" onClick={close}>
          {t("cancel")}
        </button>
        <button
          type="submit"
          form={formId}
          className="btn primary"
          disabled={file === null}
        >
          <Upload size={12} aria-hidden="true" />
          {t("submit")}
        </button>
      </>
    );
  })();

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={560}
      title={t("title")}
      description={t("description")}
      footer={footer}
    >
      <form id={formId} onSubmit={submit} noValidate>
        <ProjectImportView
          stage={stage}
          file={file ? { name: file.name, size: file.size } : null}
          percent={percent}
          result={result}
          failure={failure}
          onPick={pick}
        />
      </form>
    </Modal>
  );
};
