import type { TFunction } from "i18next";
import { useState } from "react";
import { Building2, Plus, UserRound, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useAddPackStudioGrant,
  usePackServiceAccess,
  usePackStudioAdmin,
  useRemovePackStudioGrant,
  useSetPackStudioAdmin,
  type PackStudioGrant,
} from "@entities/pack-studio";
import { adminPickers } from "@entities/session";
import { ApiError } from "@shared/api";
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
  Spinner,
  ViewTabs,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { deriveSetup, grantName, MAX_NAMES } from "../lib/setup";
import { OfficialSection } from "./OfficialSection";
import { SetupChecklist } from "./SetupChecklist";
import { AddRepoDialog, ServiceAccessSection } from "./ServiceAccessSection";

type Subject = PackStudioGrant["subject"];

const grantTitle = (grant: PackStudioGrant): string =>
  grant.name ?? grant.subject_id;

/** Почта и слово «человек» или «группа ФКН»: из каких частей состоит строка, решает тип. */
const grantDetail = (grant: PackStudioGrant, t: TFunction): string[] =>
  grant.subject === "user"
    ? [grant.email, t("grants.person")].filter((x): x is string => !!x)
    : [
        [t("grants.group"), grant.org_name ?? grant.org_slug]
          .filter(Boolean)
          .join(" "),
      ];

/** Окно «Выдать доступ»: человеку поиском или группе организации (сначала организация). */
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

/** «Анна Петрова и группа «Методисты»»: имена списком по правилам языка. */
const listOf = (items: string[], lang: string): string =>
  new Intl.ListFormat(lang, { style: "long", type: "conjunction" }).format(
    items,
  );

/**
 * Админка, «Студия шаблонов» (pack-studio-ux.md, 5.9): сверху чек-лист «что
 * осталось», ниже кто может править шаблоны, подключённые репозитории и
 * официальные шаблоны. Включение раздела и права те же, что в template-studio.md
 * (D4 и 3.3): админ установки имеет доступ всегда, о слиянии решает хостинг git.
 */
export const PackStudioAdminPage = () => {
  const { t, i18n } = useTranslation("adminPackStudio");
  const admin = usePackStudioAdmin();
  const repos = usePackServiceAccess();
  const toggle = useSetPackStudioAdmin();
  const remove = useRemovePackStudioGrant();
  const [granting, setGranting] = useState(false);
  const [connecting, setConnecting] = useState(false);

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
  const reposMissing =
    repos.error instanceof ApiError &&
    repos.error.code === "service_access_not_found";
  const setup = deriveSetup({
    enabled: data.enabled,
    grants: data.grants.length,
    repos: reposMissing ? null : (repos.data?.length ?? 0),
  });
  const groupLabel = (name: string) => t("setup.access.group", { name });
  const names = data.grants.map((g) => grantName(g, groupLabel));
  const shown = listOf(names.slice(0, MAX_NAMES), i18n.language);
  const accessHint =
    names.length === 0
      ? t("setup.access.hintTodo")
      : t("setup.access.hintDone", {
          who:
            names.length > MAX_NAMES
              ? t("setup.access.more", {
                  count: names.length - MAX_NAMES,
                  list: names.slice(0, MAX_NAMES).join(", "),
                })
              : shown,
        });
  const repoHint = repos.isError
    ? t("setup.repo.hintError")
    : (repos.data?.length ?? 0) > 0
      ? t("setup.repo.hintDone", {
          list: (repos.data ?? []).map((r) => r.label).join(", "),
        })
      : t("setup.repo.hintTodo");
  return (
    <div
      className="flex flex-col"
      style={{ gap: "1rem" }}
      data-testid="ps-admin"
    >
      <PageHeader title={t("title")} description={t("lead")} />
      <SetupChecklist
        setup={setup}
        enabled={data.enabled}
        locked={data.locked}
        toggling={toggle.isPending}
        onToggle={(next) => {
          toggle.mutate(next);
        }}
        accessHint={accessHint}
        repoHint={repoHint}
        onGrant={() => {
          setGranting(true);
        }}
        onConnect={() => {
          setConnecting(true);
        }}
      />
      {toggle.isError && (
        <Notice tone="err" role="alert" text={packErrorText(toggle.error)} />
      )}
      <Section
        title={t("grants.title")}
        description={t("grants.lead")}
        testId="ps-grants"
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
            testId="ps-grants-empty"
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
                  ...grantDetail(grant, t),
                  t("grants.since", { when: formatPastTime(grant.created_at) }),
                ].join(" · ")}
                meta={
                  <Button
                    size="xs"
                    variant="ghost"
                    aria-label={t("grants.revoke", { name: grantTitle(grant) })}
                    disabled={remove.isPending}
                    onClick={() => {
                      remove.mutate(grant.id);
                    }}
                    data-testid="ps-grant-revoke"
                  >
                    {t("grants.revokeLabel")}
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
      <ServiceAccessSection
        list={repos}
        onAdd={() => {
          setConnecting(true);
        }}
      />
      <OfficialSection />
      <GrantDialog
        isOpen={granting}
        onClose={() => {
          setGranting(false);
        }}
      />
      <AddRepoDialog
        isOpen={connecting}
        onClose={() => {
          setConnecting(false);
        }}
      />
    </div>
  );
};
