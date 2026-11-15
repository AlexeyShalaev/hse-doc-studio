import { useId, useMemo, useState } from "react";
import { BadgeCheck, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCredentials } from "@entities/git-remote";
import {
  packErrorText,
  useOpenPackOfficial,
  usePackOfficial,
  type PackOfficial,
  type PackWorkspace,
} from "@entities/pack-studio";
import { RepoTokenHelp } from "@features/git-remote";
import { Button, Modal, Select } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { hostOfUrl } from "../lib/hostOfUrl";

/** Где человек добавляет токен: «Настройки», раздел «Доступы git». */
const GIT_ACCESS_SETTINGS = "/settings/git-access";

export type OfficialPacksDialogProps = {
  official: PackOfficial;
  isOpen: boolean;
  onClose: () => void;
  onOpened: (workspace: PackWorkspace) => void;
};

/**
 * Доступ к официальным пакам (template-studio.md, 4.7): только свой токен
 * GitHub (PR создают люди своим аккаунтом); без токена окно объясняет, какой
 * выпустить.
 */
export const OfficialPacksDialog = ({
  official,
  isOpen,
  onClose,
  onOpened,
}: OfficialPacksDialogProps) => {
  const { t } = useTranslation("packStudio");
  const open = useOpenPackOfficial();
  const credentials = useCredentials(isOpen);
  const uid = useId();
  const repo = official.repo;
  const host = repo ? hostOfUrl(repo.url) : null;
  const tokens = useMemo(
    () =>
      (credentials.data ?? []).filter(
        (c) => host !== null && c.host.toLowerCase() === host,
      ),
    [credentials.data, host],
  );
  const [credentialId, setCredentialId] = useState<string | null>(null);
  const tokenId = credentialId ?? tokens[0]?.id ?? null;
  const nothing = tokens.length === 0;

  const close = () => {
    if (open.isPending) return;
    open.reset();
    setCredentialId(null);
    onClose();
  };
  const submit = () => {
    if (tokenId === null) return;
    open.mutate(
      { credential_id: tokenId },
      {
        onSuccess: (workspace) => {
          setCredentialId(null);
          onOpened(workspace);
        },
      },
    );
  };

  if (!repo) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("official.title")}
      description={t("official.dialogLead")}
      width={580}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={open.isPending || tokenId === null}
            onClick={submit}
            data-testid="official-submit"
          >
            {t("official.submit")}
          </Button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="official-dialog"
      >
        {tokens.length > 0 && (
          <p className="ps-dialog-text" data-testid="official-access-token">
            {t("official.token.hint")}
          </p>
        )}
        {tokens.length > 1 && (
          <div className="field">
            <label htmlFor={`${uid}-credential`}>
              {t("create.credential")}
            </label>
            <Select
              id={`${uid}-credential`}
              value={tokenId ?? ""}
              onValueChange={setCredentialId}
              options={tokens.map((c) => ({
                value: c.id,
                label: `${c.label} · ${c.host}`,
              }))}
              ariaLabel={t("create.credential")}
            />
          </div>
        )}
        {nothing && (
          <div data-testid="official-nothing">
            <Notice tone="info" role="status" text={t("official.none.lead")} />
          </div>
        )}
        <details className="sync-details" open={nothing}>
          <summary>{t("official.none.token")}</summary>
          <div
            className="flex flex-col"
            style={{ gap: "0.5rem", marginTop: "0.5rem" }}
          >
            <p className="ps-dialog-text">{t("official.none.steps")}</p>
            <RepoTokenHelp url={repo.url} profile="packs" defaultOpen />
            <a href={GIT_ACCESS_SETTINGS} className="ps-dialog-text">
              {t("official.none.settings")}
            </a>
          </div>
        </details>
        {open.isError && (
          <Notice tone="err" role="alert" text={packErrorText(open.error)} />
        )}
      </div>
    </Modal>
  );
};

export type OfficialPacksCardProps = {
  onOpen: (id: string) => void;
};

/**
 * Карточка «Официальные паки» на главной Студии шаблонов: паки репозитория
 * Студии и вклад в них через PR. Пустой адрес в настройках установки прячет её.
 */
export const OfficialPacksCard = ({ onOpen }: OfficialPacksCardProps) => {
  const { t } = useTranslation("packStudio");
  const official = usePackOfficial();
  const [choosing, setChoosing] = useState(false);
  const data = official.data;
  if (!data?.repo) return null;
  const existing = data.workspace_id;

  return (
    <section className="ps-ws-card" data-testid="official-card">
      <span className="ps-ws-icon" aria-hidden="true">
        <BadgeCheck size="1.125rem" />
      </span>
      <div className="ps-ws-body">
        <div className="ps-ws-title">
          <strong>{t("official.title")}</strong>
        </div>
        <div className="ps-ws-meta">{t("official.lead")}</div>
        <div className="ps-ws-meta mono truncate" title={data.repo.web_url}>
          <a href={data.repo.web_url} target="_blank" rel="noopener noreferrer">
            <ExternalLink size="0.6875rem" aria-hidden="true" />{" "}
            {data.repo.web_url.replace(/^https:\/\//, "")}
          </a>
          {` · ${data.repo.packs_path} · ${data.repo.base_branch}`}
        </div>
      </div>
      <div className="ps-ws-actions">
        <Button
          size="sm"
          onClick={() => {
            if (existing) onOpen(existing);
            else setChoosing(true);
          }}
          data-testid="official-open"
        >
          {existing ? t("workspaces.open") : t("official.start")}
        </Button>
      </div>
      <OfficialPacksDialog
        official={data}
        isOpen={choosing}
        onClose={() => {
          setChoosing(false);
        }}
        onOpened={(workspace) => {
          setChoosing(false);
          onOpen(workspace.id);
        }}
      />
    </section>
  );
};
