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
import { AddTokenForm } from "@features/git-remote";
import { Button, Input, Modal, Select, ViewTabs } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { hostOfUrl } from "../lib/hostOfUrl";
import "./space-list.css";

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
  /** Что подключаем: репозиторий git или папку на диске (папка только в локальной Студии). */
  kind: PackWorkspace["kind"];
  /** Служебный доступ задаёт админ сервера: в локальной Студии его нет. */
  allowServiceAccess?: boolean | undefined;
  renderFolderPicker?: FolderPickerRender | undefined;
};

const NO_CREDENTIAL = "none";
/** Пункт «Новый токен»: поле токена прямо в окне. */
const NEW_TOKEN = "new";
const DEFAULT_PACKS_PATH = "packs";

const trimmed = (value: string): string | null => {
  const text = value.trim();
  return text === "" ? null : text;
};

/**
 * Подключение пространства (pack-studio-ux.md, 5.2). Одно поле на виду: адрес
 * репозитория (или папка). Всё остальное под «Дополнительно» с прежними
 * умолчаниями. Токен добавляется здесь же, одной кнопкой под полем. Клон идёт
 * в фоне: пространство сразу появляется в списке как «Подключаем…».
 */
export const CreateWorkspaceDialog = ({
  isOpen,
  onClose,
  onCreated,
  kind,
  allowServiceAccess = false,
  renderFolderPicker,
}: CreateWorkspaceDialogProps) => {
  const { t } = useTranslation("packStudio");
  const create = useCreatePackWorkspace();
  const credentials = useCredentials(isOpen && kind === "git");
  const [url, setUrl] = useState("");
  // null: человек не выбирал, берётся подходящий токен для хоста или никакого.
  // Выбор помнит хост: адрес поменяли на другой, и прежний токен уже не подходит.
  const [picked, setPicked] = useState<{ id: string; host: string } | null>(
    null,
  );
  const [addingToken, setAddingToken] = useState(false);
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
  const hostCredentials = useMemo(
    () =>
      host === null
        ? []
        : (credentials.data ?? []).filter((c) => c.host.toLowerCase() === host),
    [credentials.data, host],
  );
  const credentialId =
    picked !== null && picked.host === host
      ? picked.id
      : (hostCredentials[0]?.id ?? NO_CREDENTIAL);
  const pick = (id: string) => {
    setPicked(host === null ? null : { id, host });
  };
  const credential = hostCredentials.find((c) => c.id === credentialId);
  const service = allowServiceAccess && access === "service";
  const plainHttp = url.trim().toLowerCase().startsWith("http://");
  const tokenForm = host !== null && addingToken && !service;

  const credentialOptions = [
    { value: NO_CREDENTIAL, label: t("create.noCredential") },
    ...hostCredentials.map((c) => ({
      value: c.id,
      label: `${c.label} · ${c.host}`,
    })),
    { value: NEW_TOKEN, label: t("create.newToken") },
  ];

  const canSubmit =
    !create.isPending &&
    (kind === "git"
      ? trimmed(url) !== null && (service || !tokenForm)
      : trimmed(folder) !== null);

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

  const accessLine = (() => {
    if (kind !== "git" || service) return null;
    if (tokenForm) return t("create.newTokenHint");
    if (credential) return t("create.withToken", { name: credential.label });
    return t("create.openHint");
  })();

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={kind === "git" ? t("create.title") : t("create.titleFolder")}
      width={520}
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
            {t("create.submit")}
          </Button>
        </>
      }
    >
      <div className="sp-connect" data-testid="ws-create-dialog">
        {kind === "git" ? (
          <div className="flex flex-col" style={{ gap: "0.375rem" }}>
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
            {accessLine !== null && (
              <p className="sp-access-line" data-testid="ws-create-access">
                <span>{accessLine}</span>
                {host !== null && !tokenForm && !credential && (
                  <button
                    type="button"
                    className="sp-link-btn"
                    onClick={() => {
                      setAddingToken(true);
                    }}
                    data-testid="ws-create-add-token"
                  >
                    {t("create.addToken")}
                  </button>
                )}
                {tokenForm && (
                  <button
                    type="button"
                    className="sp-link-btn"
                    onClick={() => {
                      setAddingToken(false);
                      pick(NO_CREDENTIAL);
                    }}
                  >
                    {t("create.noToken")}
                  </button>
                )}
              </p>
            )}
            {service && (
              <p
                className="sp-access-line"
                data-testid="ws-create-service-hint"
              >
                {t("create.access.serviceHint")}
              </p>
            )}
            {tokenForm && (
              <div data-testid="ws-create-token">
                <AddTokenForm
                  url={url}
                  profile="packs"
                  helpOpen={false}
                  autoFocus={false}
                  onSaved={(saved) => {
                    pick(saved.id);
                    setAddingToken(false);
                  }}
                />
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col" style={{ gap: "0.5rem" }}>
            <Input
              label={t("create.folder")}
              hint={t("create.folderHint")}
              placeholder="/Users/me/hse-doc-studio"
              value={folder}
              onChange={(e) => {
                setFolder(e.target.value);
              }}
              isMono
              autoFocus
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
                  data-testid="ws-create-pick-folder"
                >
                  <FolderOpen size="0.75rem" />
                  {t("create.pickFolder")}
                </Button>
              </div>
            )}
          </div>
        )}
        {kind === "git" && plainHttp && (
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
        <details className="sp-more" data-testid="ws-create-more">
          <summary>
            {kind === "git" ? t("create.advanced") : t("create.advancedFolder")}{" "}
            <span className="sp-more-list">
              {kind === "git"
                ? t("create.advancedList")
                : t("create.advancedFolderList")}
            </span>
          </summary>
          <div className="sp-more-fields">
            {kind === "git" && (
              <>
                <Input
                  label={t("create.branch")}
                  hint={t("create.branchHint")}
                  value={branch}
                  onChange={(e) => {
                    setBranch(e.target.value);
                  }}
                  isMono
                  data-testid="ws-create-branch"
                />
                {allowServiceAccess && (
                  <ViewTabs<Access>
                    views={[
                      {
                        value: "personal",
                        label: t("create.access.personal"),
                      },
                      { value: "service", label: t("create.access.service") },
                    ]}
                    value={access}
                    onChange={setAccess}
                  />
                )}
                {!service && host !== null && (
                  <div className="field">
                    <label htmlFor={credentialFieldId}>
                      {t("create.credential")}
                    </label>
                    <Select
                      id={credentialFieldId}
                      value={tokenForm ? NEW_TOKEN : credentialId}
                      onValueChange={(value) => {
                        if (value === NEW_TOKEN) {
                          setAddingToken(true);
                        } else {
                          setAddingToken(false);
                          pick(value);
                        }
                      }}
                      options={credentialOptions}
                      ariaLabel={t("create.credential")}
                    />
                  </div>
                )}
              </>
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
          </div>
        </details>
        {create.isError && (
          <Notice tone="err" role="alert" text={packErrorText(create.error)} />
        )}
        <p className="sp-access-line" data-testid="ws-create-note">
          {kind === "git" ? t("create.footGit") : t("create.footFolder")}
        </p>
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
