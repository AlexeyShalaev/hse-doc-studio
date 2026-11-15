import { useState } from "react";
import { Building2, Plus, Trash2, UserRound, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useAddPackStudioGrant,
  usePackStudioAdmin,
  useRemovePackStudioGrant,
  useSetPackStudioAdmin,
  type PackStudioGrant,
} from "@entities/pack-studio";
import { adminPickers } from "@entities/session";
import { formatPastTime, type PickerItem } from "@shared/lib";
import {
  Button,
  EmptyState,
  ErrorState,
  ListRow,
  Modal,
  PageHeader,
  Picker,
  Section,
  SectionList,
  SettingRow,
  Spinner,
  ViewTabs,
} from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { Notice } from "@shared/ui/ConflictKit";
import { ServiceAccessSection } from "./ServiceAccessSection";

type Subject = PackStudioGrant["subject"];

const grantTitle = (grant: PackStudioGrant): string =>
  grant.name ?? grant.subject_id;

const grantDetail = (grant: PackStudioGrant): string | null =>
  grant.subject === "user"
    ? grant.email
    : [grant.org_name ?? grant.org_slug].filter(Boolean).join(" · ") || null;

/** Окно «Выдать право»: человеку поиском или группе организации (сначала организация). */
const GrantDialog = ({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminPackStudio");
  const add = useAddPackStudioGrant();
  const [subject, setSubject] = useState<Subject>("user");
  const [user, setUser] = useState<PickerItem | null>(null);
  const [org, setOrg] = useState<PickerItem | null>(null);
  const [group, setGroup] = useState<PickerItem | null>(null);
  const chosen = subject === "user" ? user : group;

  const close = () => {
    add.reset();
    setUser(null);
    setOrg(null);
    setGroup(null);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("grant.title")}
      description={t("grant.lead")}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("grant.cancel")}
          </Button>
          <Button
            disabled={chosen === null || add.isPending}
            data-testid="ps-grant-submit"
            onClick={() => {
              if (!chosen) return;
              add.mutate(
                subject === "user"
                  ? { user_id: chosen.id }
                  : { group_id: chosen.id },
                { onSuccess: close },
              );
            }}
          >
            {t("grant.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.875rem" }}>
        <ViewTabs<Subject>
          views={[
            { value: "user", label: t("grant.toUser") },
            { value: "group", label: t("grant.toGroup") },
          ]}
          value={subject}
          onChange={setSubject}
        />
        {subject === "user" ? (
          <Picker
            source={adminPickers.users({ status: "active" })}
            value={user}
            onChange={setUser}
            label={t("grant.user")}
            placeholder={t("grant.userPlaceholder")}
            testId="ps-grant-user"
          />
        ) : (
          <>
            <Picker
              source={adminPickers.orgs()}
              value={org}
              onChange={(item) => {
                setOrg(item);
                setGroup(null);
              }}
              label={t("grant.org")}
              placeholder={t("grant.orgPlaceholder")}
              testId="ps-grant-org"
            />
            <Picker
              source={adminPickers.orgGroups(org?.id ?? "")}
              value={group}
              onChange={setGroup}
              label={t("grant.group")}
              placeholder={t("grant.groupPlaceholder")}
              disabled={org === null}
              testId="ps-grant-group"
            />
          </>
        )}
        {add.isError && (
          <Notice tone="err" role="alert" text={packErrorText(add.error)} />
        )}
      </div>
    </Modal>
  );
};

/**
 * Админка, «Студия шаблонов» (template-studio.md, D4 и 3.3): включение раздела
 * на сервере и право «Автор шаблонов» людям и группам организаций. Админ
 * установки имеет право всегда; решение о слиянии принимает хостинг git.
 */
export const PackStudioAdminPage = () => {
  const { t } = useTranslation("adminPackStudio");
  const admin = usePackStudioAdmin();
  const toggle = useSetPackStudioAdmin();
  const remove = useRemovePackStudioGrant();
  const [granting, setGranting] = useState(false);

  if (admin.isPending) {
    return (
      <>
        <PageHeader title={t("title")} description={t("lead")} />
        <Spinner />
      </>
    );
  }
  if (admin.isError) {
    return (
      <>
        <PageHeader title={t("title")} description={t("lead")} />
        <ErrorState
          description={packErrorText(admin.error)}
          onRetry={() => void admin.refetch()}
        />
      </>
    );
  }
  const data = admin.data;
  return (
    <div
      className="flex flex-col"
      style={{ gap: "1rem" }}
      data-testid="ps-admin"
    >
      <PageHeader title={t("title")} description={t("lead")} />
      <Section title={t("section.title")}>
        <SettingRow
          label={t("section.enabled")}
          hint={data.locked ? t("section.locked") : t("section.enabledHint")}
          locked={data.locked}
        >
          <Switch
            checked={data.enabled}
            disabled={data.locked || toggle.isPending}
            onChange={(next) => {
              toggle.mutate(next);
            }}
            label={t("section.enabled")}
            testId="ps-admin-enabled"
          />
        </SettingRow>
        {toggle.isError && (
          <Notice tone="err" role="alert" text={packErrorText(toggle.error)} />
        )}
      </Section>
      <Section
        title={t("grants.title")}
        description={t("grants.lead")}
        actions={
          <Button
            size="sm"
            onClick={() => {
              setGranting(true);
            }}
            data-testid="ps-grant-open"
          >
            <Plus size="0.875rem" />
            {t("grants.add")}
          </Button>
        }
        flush={data.grants.length > 0}
      >
        {data.grants.length === 0 ? (
          <EmptyState
            compact
            icon={<Users size="1.25rem" />}
            title={t("grants.emptyTitle")}
            description={t("grants.emptyLead")}
          />
        ) : (
          <SectionList>
            {data.grants.map((grant) => (
              <ListRow
                key={grant.id}
                testId={`ps-grant-${grant.id}`}
                icon={
                  grant.subject === "user" ? (
                    <UserRound size="0.875rem" />
                  ) : (
                    <Building2 size="0.875rem" />
                  )
                }
                title={grantTitle(grant)}
                description={[
                  grant.subject === "user"
                    ? t("grants.person")
                    : t("grants.group"),
                  grantDetail(grant),
                  t("grants.since", { when: formatPastTime(grant.created_at) }),
                ]
                  .filter(Boolean)
                  .join(" · ")}
                meta={
                  <Button
                    size="xs"
                    variant="ghost"
                    aria-label={t("grants.revoke", { name: grantTitle(grant) })}
                    title={t("grants.revoke", { name: grantTitle(grant) })}
                    disabled={remove.isPending}
                    onClick={() => {
                      remove.mutate(grant.id);
                    }}
                    data-testid="ps-grant-revoke"
                  >
                    <Trash2 size="0.75rem" />
                  </Button>
                }
              />
            ))}
          </SectionList>
        )}
        {remove.isError && (
          <Notice tone="err" role="alert" text={packErrorText(remove.error)} />
        )}
      </Section>
      <ServiceAccessSection />
      <GrantDialog
        isOpen={granting}
        onClose={() => {
          setGranting(false);
        }}
      />
    </div>
  );
};
