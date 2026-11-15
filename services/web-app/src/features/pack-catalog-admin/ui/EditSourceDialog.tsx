import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  catalogErrorText,
  useReplaceArchive,
  useUpdateSource,
  type CatalogSource,
} from "@entities/pack-catalog";
import { Button, Input, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { accessComplete, accessOf, updateRequest } from "../lib/access";
import { archiveProblem } from "../lib/archiveProblem";
import { ArchivePicker } from "./ArchivePicker";
import { AccessPicker, CheckField } from "./fields";

/** Поля «Изменить»: название, ref, папка паков, доступ, замена встроенного, отслеживание. */
const EditForm = ({
  source,
  onClose,
}: {
  source: CatalogSource;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const update = useUpdateSource();
  const git = source.kind === "git";
  const [label, setLabel] = useState(source.label);
  const [packsPath, setPacksPath] = useState(source.packs_path);
  const [ref, setRef] = useState(source.ref ?? "");
  const [access, setAccess] = useState(accessOf(source));
  const [replaceBuiltin, setReplaceBuiltin] = useState(source.replace_builtin);
  const [track, setTrack] = useState(source.track);
  const body = updateRequest(source, {
    label,
    packsPath,
    ref,
    access,
    replaceBuiltin,
    track,
  });
  const changed = Object.keys(body).length > 0;

  const close = () => {
    if (update.isPending) return;
    update.reset();
    onClose();
  };

  return (
    <Modal
      isOpen
      onClose={close}
      title={t("edit.title", { name: source.label })}
      description={t("edit.lead")}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={
              !changed ||
              update.isPending ||
              (git && !accessComplete(access)) ||
              label.trim() === ""
            }
            onClick={() => {
              update.mutate({ id: source.id, body }, { onSuccess: onClose });
            }}
            data-testid="pc-edit-submit"
          >
            {update.isPending && <Spinner size="sm" />}
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.875rem" }}>
        <Input
          label={t("add.label")}
          value={label}
          maxLength={200}
          onChange={(e) => {
            setLabel(e.target.value);
          }}
          data-testid="pc-edit-label"
        />
        {git && (
          <Input
            label={t("add.ref")}
            hint={t("add.refHint")}
            value={ref}
            maxLength={200}
            onChange={(e) => {
              setRef(e.target.value);
            }}
            isMono
            data-testid="pc-edit-ref"
          />
        )}
        <Input
          label={t("add.packsPath")}
          hint={git ? t("add.packsPathGitHint") : t("add.packsPathArchiveHint")}
          value={packsPath}
          maxLength={512}
          onChange={(e) => {
            setPacksPath(e.target.value);
          }}
          isMono
          data-testid="pc-edit-packs-path"
        />
        {git && (
          <AccessPicker
            url={source.url ?? ""}
            value={access}
            onChange={setAccess}
            enabled
          />
        )}
        <CheckField
          checked={replaceBuiltin}
          onChange={setReplaceBuiltin}
          label={t("add.replaceBuiltin")}
          hint={t("add.replaceBuiltinHint")}
          testId="pc-edit-replace"
        />
        {git && (
          <CheckField
            checked={track}
            onChange={setTrack}
            label={t("add.track")}
            hint={t("add.trackHint")}
            testId="pc-edit-track"
          />
        )}
        {update.isError && (
          <Notice
            tone="err"
            role="alert"
            text={catalogErrorText(update.error)}
          />
        )}
      </div>
    </Modal>
  );
};

/** «Изменить» источник; форма пересоздаётся на каждый источник, поля берутся из него. */
export const EditSourceDialog = ({
  source,
  onClose,
}: {
  source: CatalogSource | null;
  onClose: () => void;
}) =>
  source ? (
    <EditForm key={source.id} source={source} onClose={onClose} />
  ) : null;

const ReplaceForm = ({
  source,
  maxArchiveBytes,
  onClose,
  onReplaced,
}: {
  source: CatalogSource;
  maxArchiveBytes: number;
  onClose: () => void;
  onReplaced: (source: CatalogSource) => void;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const replace = useReplaceArchive();
  const [file, setFile] = useState<File | null>(null);
  const problem = file ? archiveProblem(file, maxArchiveBytes) : null;

  const close = () => {
    if (replace.isPending) return;
    replace.reset();
    onClose();
  };

  return (
    <Modal
      isOpen
      onClose={close}
      title={t("replace.title", { name: source.label })}
      description={t("replace.lead")}
      width={540}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={file === null || problem !== null || replace.isPending}
            onClick={() => {
              if (!file) return;
              replace.mutate(
                { id: source.id, file, name: file.name },
                { onSuccess: onReplaced },
              );
            }}
            data-testid="pc-replace-submit"
          >
            {replace.isPending && <Spinner size="sm" />}
            {replace.isPending ? t("add.uploading") : t("replace.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.875rem" }}>
        <ArchivePicker
          file={file}
          onFile={setFile}
          maxBytes={maxArchiveBytes}
          disabled={replace.isPending}
        />
        {replace.isError && (
          <Notice
            tone="err"
            role="alert"
            text={catalogErrorText(replace.error)}
          />
        )}
      </div>
    </Modal>
  );
};

/** «Заменить архив» у источника-архива: новый файл, затем проверка и применение. */
export const ReplaceArchiveDialog = ({
  source,
  maxArchiveBytes,
  onClose,
  onReplaced,
}: {
  source: CatalogSource | null;
  maxArchiveBytes: number;
  onClose: () => void;
  /** Архив загружен: дальше его проверка. */
  onReplaced: (source: CatalogSource) => void;
}) =>
  source ? (
    <ReplaceForm
      key={source.id}
      source={source}
      maxArchiveBytes={maxArchiveBytes}
      onClose={onClose}
      onReplaced={onReplaced}
    />
  ) : null;
