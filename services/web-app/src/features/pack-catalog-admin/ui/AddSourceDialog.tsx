import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  catalogErrorText,
  useAddArchiveSource,
  useAddGitSource,
  type CatalogSource,
} from "@entities/pack-catalog";
import { Button, Input, Modal, Spinner, ViewTabs } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  accessComplete,
  gitSourceRequest,
  type AccessChoice,
} from "../lib/access";
import { archiveProblem } from "../lib/archiveProblem";
import { ArchivePicker } from "./ArchivePicker";
import { AccessPicker, CheckField } from "./fields";

type Tab = "git" | "archive";

const DEFAULT_PACKS_PATH = "packs";

/**
 * «Добавить источник»: git (адрес, папка паков, тег, ветка или sha, доступ) или архив
 * .zip и .tar.gz для закрытых контуров. После добавления источник проверяют и применяют.
 */
export const AddSourceDialog = ({
  isOpen,
  onClose,
  onAdded,
  maxArchiveBytes,
}: {
  isOpen: boolean;
  onClose: () => void;
  onAdded: (source: CatalogSource) => void;
  maxArchiveBytes: number;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const addGit = useAddGitSource();
  const addArchive = useAddArchiveSource();
  const [tab, setTab] = useState<Tab>("git");
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [packsPath, setPacksPath] = useState(DEFAULT_PACKS_PATH);
  const [archivePath, setArchivePath] = useState("");
  const [ref, setRef] = useState("");
  const [access, setAccess] = useState<AccessChoice>({ kind: "none" });
  const [insecure, setInsecure] = useState(false);
  const [replaceBuiltin, setReplaceBuiltin] = useState(false);
  const [track, setTrack] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const pending = addGit.isPending || addArchive.isPending;
  const error = tab === "git" ? addGit.error : addArchive.error;

  const reset = () => {
    addGit.reset();
    addArchive.reset();
    setTab("git");
    setUrl("");
    setLabel("");
    setPacksPath(DEFAULT_PACKS_PATH);
    setArchivePath("");
    setRef("");
    setAccess({ kind: "none" });
    setInsecure(false);
    setReplaceBuiltin(false);
    setTrack(false);
    setFile(null);
  };

  const close = () => {
    if (pending) return;
    reset();
    onClose();
  };

  const done = (source: CatalogSource) => {
    reset();
    onAdded(source);
  };

  const plainHttp = url.trim().toLowerCase().startsWith("http://");
  const fileProblem = file ? archiveProblem(file, maxArchiveBytes) : null;
  const canSubmit =
    !pending &&
    (tab === "git"
      ? url.trim() !== "" && accessComplete(access)
      : file !== null && fileProblem === null);

  const submit = () => {
    if (tab === "git") {
      addGit.mutate(
        gitSourceRequest({
          url,
          label,
          packsPath,
          ref,
          access,
          insecureHttp: insecure,
          replaceBuiltin,
          track,
        }),
        { onSuccess: done },
      );
      return;
    }
    if (!file) return;
    addArchive.mutate(
      {
        file,
        fields: {
          name: file.name,
          label,
          packsPath: archivePath,
          replaceBuiltin,
        },
      },
      { onSuccess: done },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("add.title")}
      description={t("add.lead")}
      width={580}
      footer={
        <>
          <Button variant="secondary" onClick={close} disabled={pending}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={!canSubmit}
            onClick={submit}
            data-testid="pc-add-submit"
          >
            {pending && <Spinner size="sm" />}
            {pending && tab === "archive"
              ? t("add.uploading")
              : t("add.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.875rem" }}>
        <ViewTabs<Tab>
          views={[
            { value: "git", label: t("add.tabGit") },
            { value: "archive", label: t("add.tabArchive") },
          ]}
          value={tab}
          onChange={setTab}
        />
        {tab === "git" ? (
          <>
            <Input
              label={t("add.url")}
              placeholder="https://gitlab.example.org/fcs/packs.git"
              value={url}
              maxLength={2048}
              onChange={(e) => {
                setUrl(e.target.value);
              }}
              isMono
              autoFocus
              data-testid="pc-add-url"
            />
            <Input
              label={t("add.label")}
              hint={t("add.labelHint")}
              value={label}
              maxLength={200}
              onChange={(e) => {
                setLabel(e.target.value);
              }}
              data-testid="pc-add-label"
            />
            <Input
              label={t("add.packsPath")}
              hint={t("add.packsPathGitHint")}
              value={packsPath}
              maxLength={512}
              onChange={(e) => {
                setPacksPath(e.target.value);
              }}
              isMono
              data-testid="pc-add-packs-path"
            />
            <Input
              label={t("add.ref")}
              hint={t("add.refHint")}
              value={ref}
              maxLength={200}
              onChange={(e) => {
                setRef(e.target.value);
              }}
              isMono
              data-testid="pc-add-ref"
            />
            <AccessPicker
              url={url}
              value={access}
              onChange={setAccess}
              enabled={isOpen}
            />
            {plainHttp && (
              <CheckField
                checked={insecure}
                onChange={setInsecure}
                label={t("add.insecureHttp")}
              />
            )}
            <CheckField
              checked={replaceBuiltin}
              onChange={setReplaceBuiltin}
              label={t("add.replaceBuiltin")}
              hint={t("add.replaceBuiltinHint")}
              testId="pc-add-replace"
            />
            <CheckField
              checked={track}
              onChange={setTrack}
              label={t("add.track")}
              hint={t("add.trackHint")}
              testId="pc-add-track"
            />
          </>
        ) : (
          <>
            <ArchivePicker
              file={file}
              onFile={setFile}
              maxBytes={maxArchiveBytes}
              disabled={pending}
            />
            <Input
              label={t("add.label")}
              hint={t("add.labelHint")}
              value={label}
              maxLength={200}
              onChange={(e) => {
                setLabel(e.target.value);
              }}
              data-testid="pc-add-label"
            />
            <Input
              label={t("add.packsPath")}
              hint={t("add.packsPathArchiveHint")}
              value={archivePath}
              maxLength={512}
              onChange={(e) => {
                setArchivePath(e.target.value);
              }}
              isMono
              data-testid="pc-add-archive-path"
            />
            <CheckField
              checked={replaceBuiltin}
              onChange={setReplaceBuiltin}
              label={t("add.replaceBuiltin")}
              hint={t("add.replaceBuiltinHint")}
            />
          </>
        )}
        {error && (
          <Notice tone="err" role="alert" text={catalogErrorText(error)} />
        )}
      </div>
    </Modal>
  );
};
