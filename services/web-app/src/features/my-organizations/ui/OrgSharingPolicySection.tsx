import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useOrgSharingPolicy,
  useSaveOrgSharingPolicy,
  type LinkRole,
  type OrgLinksMode,
  type OrgSharingPolicy,
} from "@entities/share-link";
import { toast } from "@shared/lib";
import { Button, Modal, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import {
  SHARING_MODES as MODES,
  SHARING_ROLES as ROLES,
  tightens,
} from "../lib/sharing";
import "./orgSharing.css";

const MODE_KEY = {
  any: "linksAny",
  org_only: "linksOrgOnly",
  off: "linksOff",
} as const;

export type OrgSharingPolicyViewProps = {
  orgName: string;
  status: "loading" | "error" | "ready";
  policy: OrgSharingPolicy | null;
  saving?: boolean;
  onSave: (next: OrgSharingPolicy) => void;
  onRetry?: () => void;
};

/** Section «Общий доступ» организации (10.5): ссылки, предел роли, NDA, чужие домены. */
export const OrgSharingPolicyView = (props: OrgSharingPolicyViewProps) => {
  const { t } = useTranslation("organizations");
  const ids = { links: useId(), role: useId(), nda: useId(), ext: useId() };
  const [draft, setDraft] = useState<OrgSharingPolicy | null>(props.policy);
  const [confirming, setConfirming] = useState(false);

  const editable = props.policy?.editable === true;
  const dirty =
    draft !== null &&
    props.policy !== null &&
    JSON.stringify(draft) !== JSON.stringify(props.policy);
  const save = () => {
    if (!draft || !props.policy) return;
    if (tightens(props.policy, draft)) {
      setConfirming(true);
      return;
    }
    props.onSave(draft);
  };

  return (
    <section
      className="org-sharing"
      data-testid="org-sharing-policy"
      aria-label={t("sharing.title")}
    >
      <div className="org-sharing-head">
        <h5>
          {t("sharing.title")} · {props.orgName}
        </h5>
        <p>{t("sharing.description")}</p>
      </div>
      {props.status === "loading" && <Spinner size="sm" />}
      {props.status === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("sharing.loadFailed")}
          action={
            props.onRetry && (
              <button type="button" className="btn xs" onClick={props.onRetry}>
                {t("section.retry")}
              </button>
            )
          }
        />
      )}
      {props.status === "ready" && draft && (
        <div className="org-sharing-rows">
          {!editable && (
            <Notice tone="info" role="status" text={t("sharing.readOnly")} />
          )}
          <div className="org-sharing-row">
            <label htmlFor={ids.links}>{t("sharing.links")}</label>
            <div data-testid="org-sharing-links">
              <Select
                id={ids.links}
                value={draft.links}
                isDisabled={!editable}
                onValueChange={(value) => {
                  setDraft({ ...draft, links: value as OrgLinksMode });
                }}
                options={MODES.map((mode) => ({
                  value: mode,
                  label: t(`sharing.${MODE_KEY[mode]}`),
                }))}
              />
            </div>
          </div>
          <div className="org-sharing-row">
            <label htmlFor={ids.role}>{t("sharing.maxRole")}</label>
            <div data-testid="org-sharing-max-role">
              <Select
                id={ids.role}
                value={draft.max_link_role}
                isDisabled={!editable}
                onValueChange={(value) => {
                  setDraft({ ...draft, max_link_role: value as LinkRole });
                }}
                options={ROLES.map((role) => ({
                  value: role,
                  label: t(`sharing.roles.${role}`),
                }))}
              />
            </div>
          </div>
          <div className="org-sharing-row">
            <label htmlFor={ids.nda}>
              {t("sharing.nda")}
              <span className="org-sharing-hint">{t("sharing.ndaHint")}</span>
            </label>
            <Switch
              id={ids.nda}
              checked={draft.nda_public_links}
              disabled={!editable}
              onChange={(next) => {
                setDraft({ ...draft, nda_public_links: next });
              }}
              testId="org-sharing-nda"
            />
          </div>
          <div className="org-sharing-row">
            <label htmlFor={ids.ext}>{t("sharing.externalInvites")}</label>
            <Switch
              id={ids.ext}
              checked={draft.external_invites}
              disabled={!editable}
              onChange={(next) => {
                setDraft({ ...draft, external_invites: next });
              }}
              testId="org-sharing-external-invites"
            />
          </div>
          {editable && (
            <div>
              <Button
                type="button"
                size="sm"
                onClick={save}
                disabled={!dirty || props.saving}
                data-testid="org-sharing-save"
              >
                {props.saving && <Spinner size="sm" />}
                {t("sharing.save")}
              </Button>
            </div>
          )}
        </div>
      )}
      <Modal
        isOpen={confirming}
        onClose={() => {
          setConfirming(false);
        }}
        title={t("sharing.confirmTitle")}
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setConfirming(false);
              }}
            >
              {t("sharing.cancel")}
            </Button>
            <Button
              type="button"
              variant="danger"
              data-testid="org-sharing-confirm"
              onClick={() => {
                setConfirming(false);
                if (draft) props.onSave(draft);
              }}
            >
              {t("sharing.confirm")}
            </Button>
          </>
        }
      >
        <p>{t("sharing.confirmText")}</p>
      </Modal>
    </section>
  );
};

/** Политика организации с сервера: участник видит, владелец и админ правят. */
export const OrgSharingPolicySection = ({
  slug,
  name,
}: {
  slug: string;
  name: string;
}) => {
  const { t } = useTranslation("organizations");
  const policy = useOrgSharingPolicy(slug);
  const save = useSaveOrgSharingPolicy(slug);
  return (
    <OrgSharingPolicyView
      // Черновик живёт в виде: новые значения сервера пересоздают его.
      key={policy.data ? JSON.stringify(policy.data) : "loading"}
      orgName={name}
      status={policy.data ? "ready" : policy.isError ? "error" : "loading"}
      policy={policy.data ?? null}
      saving={save.isPending}
      onRetry={() => {
        void policy.refetch();
      }}
      onSave={(next) => {
        save.mutate(next, {
          onSuccess: () => {
            toast.success(t("sharing.saved"));
          },
          onError: () => {
            toast.error(t("sharing.saveFailed"));
          },
        });
      }}
    />
  );
};
