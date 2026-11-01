import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useAdminSharingSettings,
  useSaveAdminSharingSettings,
  type AdminSharingSettings,
  type LinkRole,
  type UpdateAdminSharingRequest,
} from "@entities/share-link";
import { failureCode } from "@shared/api";
import { i18n, toast } from "@shared/lib";
import { Button, Section, Select, SettingRow, Spinner } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";

const ROLES: readonly LinkRole[] = ["reader", "reviewer", "editor"];
const KEYS = {
  links: "sharing.links_enabled",
  role: "sharing.max_link_role",
  signup: "registration.project_invites_allow_signup",
} as const;

export type AdminSharingSettingsViewProps = {
  settings: AdminSharingSettings;
  saving?: boolean;
  onSave: (patch: UpdateAdminSharingRequest) => void;
};

/** «Общий доступ» в настройках установки (10.5): ссылки, предел роли, регистрация по приглашению в проект. */
export const AdminSharingSettingsView = ({
  settings,
  saving,
  onSave,
}: AdminSharingSettingsViewProps) => {
  const { t } = useTranslation("adminInstall");
  const [links, setLinks] = useState(settings.links_enabled);
  const [role, setRole] = useState<LinkRole>(settings.max_link_role);
  const [signup, setSignup] = useState(settings.project_invites_allow_signup);
  const locked = (key: string) =>
    settings.fields[key]?.locked === true ? t("sharing.lockedHint") : undefined;
  const patch: UpdateAdminSharingRequest = {
    links_enabled: links === settings.links_enabled ? null : links,
    max_link_role: role === settings.max_link_role ? null : role,
    project_invites_allow_signup:
      signup === settings.project_invites_allow_signup ? null : signup,
  };
  const dirty = Object.values(patch).some((v) => v !== null);

  return (
    <Section
      title={t("sharing.title")}
      description={t("sharing.lead")}
      testId="admin-sharing-settings"
      footer={
        <Button
          type="button"
          size="sm"
          disabled={!dirty || saving}
          onClick={() => {
            onSave(patch);
          }}
          data-testid="admin-sharing-save"
        >
          {saving && <Spinner size="sm" />}
          {t("sharing.save")}
        </Button>
      }
    >
      <SettingRow
        label={t("sharing.links")}
        hint={t("sharing.linksHint")}
        locked={locked(KEYS.links)}
        align="end"
      >
        <Switch
          checked={links}
          onChange={setLinks}
          disabled={locked(KEYS.links) !== undefined}
          label={t("sharing.links")}
          testId="admin-sharing-links-toggle"
        />
      </SettingRow>
      <SettingRow
        label={t("sharing.maxRole")}
        hint={t("sharing.maxRoleHint")}
        locked={locked(KEYS.role)}
      >
        <div data-testid="admin-sharing-max-role">
          <Select
            value={role}
            isDisabled={locked(KEYS.role) !== undefined}
            ariaLabel={t("sharing.maxRole")}
            onValueChange={(value) => {
              setRole(value as LinkRole);
            }}
            options={ROLES.map((r) => ({
              value: r,
              label: t(`sharing.roles.${r}`),
            }))}
          />
        </div>
      </SettingRow>
      <SettingRow
        label={t("sharing.inviteSignup")}
        hint={t("sharing.inviteSignupHint")}
        locked={locked(KEYS.signup)}
        align="end"
      >
        <Switch
          checked={signup}
          onChange={setSignup}
          disabled={locked(KEYS.signup) !== undefined}
          label={t("sharing.inviteSignup")}
          testId="admin-sharing-invite-signup"
        />
      </SettingRow>
    </Section>
  );
};

/** Раздел с сервером: читает и сохраняет `/api/admin/settings/sharing`. */
export const AdminSharingSettingsSection = () => {
  const { t } = useTranslation("adminInstall");
  const settings = useAdminSharingSettings();
  const save = useSaveAdminSharingSettings();
  if (!settings.data) return null;
  return (
    <AdminSharingSettingsView
      // После сохранения форма пересоздаётся с новыми значениями сервера.
      key={JSON.stringify(settings.data)}
      settings={settings.data}
      saving={save.isPending}
      onSave={(patch) => {
        save.mutate(patch, {
          onSuccess: () => {
            toast.success(t("sharing.saved"));
          },
          onError: (error) => {
            const code = failureCode(error);
            toast.error(
              code && i18n.exists(`errors:code.${code}`)
                ? i18n.t(`errors:code.${code}`)
                : i18n.t("errors:title.generic"),
            );
          },
        });
      }}
    />
  );
};
