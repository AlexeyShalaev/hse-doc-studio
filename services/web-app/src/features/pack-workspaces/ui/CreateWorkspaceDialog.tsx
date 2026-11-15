import { useId, useMemo, useState, type ReactNode } from "react";
import { FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCredentials } from "@entities/git-remote";
import {
  packErrorText,
  useCreatePackWorkspace,
  type CreatePackWorkspaceRequest,
  type PackWorkspace,
} from "@entities/pack-studio";
import { RepoTokenHelp } from "@features/git-remote";
import { Button, Input, Modal, Select, ViewTabs } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { hostOfUrl } from "../lib/hostOfUrl";

type Kind = PackWorkspace["kind"];
/** Чем ходить в репозиторий: личный доступ git или служебный доступ установки. */
type Access = "personal" | "service";

/** Окно выбора папки на диске: его даёт страница (фича выбора папки), сюда приходит только вызов. */
export type FolderPickerRender = (props: {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
}) => ReactNode;

export type CreateWorkspaceDialogProps = {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (workspace: PackWorkspace) => void;
  /** Папка на диске есть только в локальной Студии: на сервере вкладки «Папка» нет. */
  allowFolder: boolean;
  renderFolderPicker?: FolderPickerRender | undefined;
};

const NO_CREDENTIAL = "none";
const DEFAULT_PACKS_PATH = "packs";

const trimmed = (value: string): string | null => {
  const text = value.trim();
  return text === "" ? null : text;
};

/**
 * Новое рабочее пространство (template-studio.md, 4.1): репозиторий паков git с
 * доступом из «Доступов git» или папка на диске (локально). Клон идёт в фоне,
 * пространство сразу появляется в списке в состоянии «Клонируется».
 */
export const CreateWorkspaceDialog = ({
  isOpen,
  onClose,
  onCreated,
  allowFolder,
  renderFolderPicker,
}: CreateWorkspaceDialogProps) => {
  const { t } = useTranslation("packStudio");
  const create = useCreatePackWorkspace();
  const credentials = useCredentials(isOpen);
  const [kind, setKind] = useState<Kind>(allowFolder ? "folder" : "git");
  const [url, setUrl] = useState("");
  const [credentialId, setCredentialId] = useState(NO_CREDENTIAL);
  const [branch, setBranch] = useState("");
  const [packsPath, setPacksPath] = useState(DEFAULT_PACKS_PATH);
  const [folder, setFolder] = useState("");
  const [label, setLabel] = useState("");
  const [insecure, setInsecure] = useState(false);
  const [access, setAccess] = useState<Access>("personal");
  const [picking, setPicking] = useState(false);
  const insecureId = useId();
  const credentialFieldId = useId();

  const host = hostOfUrl(url);
  const credentialOptions = useMemo(() => {
    const list = (credentials.data ?? []).filter(
      (c) => host === null || c.host.toLowerCase() === host,
    );
    return [
      { value: NO_CREDENTIAL, label: t("create.noCredential") },
      ...list.map((c) => ({ value: c.id, label: `${c.label} · ${c.host}` })),
    ];
  }, [credentials.data, host, t]);
  const plainHttp = url.trim().toLowerCase().startsWith("http://");
  // Служебный доступ задаёт админ сервера: в локальной Студии (есть папки) его нет.
  const serviceAllowed = !allowFolder;
  const service = serviceAllowed && access === "service";

  const canSubmit =
    !create.isPending &&
    (kind === "git" ? trimmed(url) !== null : trimmed(folder) !== null);

  const submit = () => {
    const body: CreatePackWorkspaceRequest =
      kind === "git"
        ? {
            kind,
            url: url.trim(),
            credential_id:
              service || credentialId === NO_CREDENTIAL ? null : credentialId,
            ...(service ? { service_access: true } : {}),
            base_branch: trimmed(branch),
            packs_path: trimmed(packsPath),
            label: trimmed(label),
            insecure_http: plainHttp && insecure,
          }
        : {
            kind,
            folder: folder.trim(),
            packs_path: trimmed(
              packsPath === DEFAULT_PACKS_PATH ? "" : packsPath,
            ),
            label: trimmed(label),
          };
    create.mutate(body, {
      onSuccess: (workspace) => {
        onCreated(workspace);
      },
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("create.title")}
      description={t("create.lead")}
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={!canSubmit}
            onClick={submit}
            data-testid="ws-create-submit"
          >
            {kind === "git" ? t("create.submitGit") : t("create.submitFolder")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.875rem" }}>
        {allowFolder && (
          <ViewTabs<Kind>
            views={[
              { value: "folder", label: t("create.kind.folder") },
              { value: "git", label: t("create.kind.git") },
            ]}
            value={kind}
            onChange={setKind}
          />
        )}
        {kind === "git" ? (
          <>
            <Input
              label={t("create.url")}
              placeholder="https://github.com/owner/packs"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
              }}
              isMono
              autoFocus
              data-testid="ws-create-url"
            />
            {serviceAllowed && (
              <ViewTabs<Access>
                views={[
                  { value: "personal", label: t("create.access.personal") },
                  { value: "service", label: t("create.access.service") },
                ]}
                value={access}
                onChange={setAccess}
              />
            )}
            {service ? (
              <p className="hint" data-testid="ws-create-service-hint">
                {t("create.access.serviceHint")}
              </p>
            ) : (
              <div className="field">
                <label htmlFor={credentialFieldId}>
                  {t("create.credential")}
                </label>
                <Select
                  id={credentialFieldId}
                  value={credentialId}
                  onValueChange={setCredentialId}
                  options={credentialOptions}
                  ariaLabel={t("create.credential")}
                />
                <p className="hint">{t("create.credentialHint")}</p>
                {host !== null && (
                  <details className="sync-details">
                    <summary>{t("create.tokenHelp")}</summary>
                    <div style={{ marginTop: "0.5rem" }}>
                      <RepoTokenHelp url={url} profile="packs" />
                    </div>
                  </details>
                )}
              </div>
            )}
            {plainHttp && (
              <label
                htmlFor={insecureId}
                className="flex items-center"
                style={{ gap: "0.5rem", fontSize: "0.75rem" }}
              >
                <input
                  id={insecureId}
                  type="checkbox"
                  checked={insecure}
                  onChange={(e) => {
                    setInsecure(e.target.checked);
                  }}
                  style={{ accentColor: "var(--accent)" }}
                />
                {t("create.insecureHttp")}
              </label>
            )}
            <Input
              label={t("create.branch")}
              hint={t("create.branchHint")}
              value={branch}
              onChange={(e) => {
                setBranch(e.target.value);
              }}
              isMono
            />
          </>
        ) : (
          <div className="flex flex-col" style={{ gap: "0.375rem" }}>
            <Input
              label={t("create.folder")}
              hint={t("create.folderHint")}
              placeholder="/Users/me/hse-doc-studio"
              value={folder}
              onChange={(e) => {
                setFolder(e.target.value);
              }}
              isMono
              data-testid="ws-create-folder"
            />
            {renderFolderPicker && (
              <div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setPicking(true);
                  }}
                >
                  <FolderOpen size="0.75rem" />
                  {t("create.pickFolder")}
                </Button>
              </div>
            )}
          </div>
        )}
        <Input
          label={t("create.packsPath")}
          hint={
            kind === "git"
              ? t("create.packsPathGitHint")
              : t("create.packsPathFolderHint")
          }
          value={packsPath}
          onChange={(e) => {
            setPacksPath(e.target.value);
          }}
          isMono
        />
        <Input
          label={t("create.label")}
          hint={t("create.labelHint")}
          value={label}
          onChange={(e) => {
            setLabel(e.target.value);
          }}
          maxLength={120}
        />
        {create.isError && (
          <Notice tone="err" role="alert" text={packErrorText(create.error)} />
        )}
      </div>
      {renderFolderPicker?.({
        isOpen: picking,
        onClose: () => {
          setPicking(false);
        },
        onSelect: (path) => {
          setFolder(path);
          setPicking(false);
        },
      })}
    </Modal>
  );
};
