import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Lock, UserMinus, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import {
  ActionMenu,
  Badge,
  Button,
  DataTable,
  FilterBar,
  Input,
  Modal,
  PersonCell,
  Select,
  Spinner,
  Tooltip,
} from "@shared/ui";
import type { AdminOrgMember, OrgRoleName } from "@entities/session";
import type { Failure } from "../lib/failure";
import { formatDate } from "../lib/format";
import {
  assignableRoles,
  canEditMember,
  isLastOwner,
  ROLES,
  type Viewer,
} from "../lib/permissions";
import { FailureNotice } from "./parts";

export type MembersViewProps = {
  status: "loading" | "error" | "ready";
  members: readonly AdminOrgMember[];
  viewer: Viewer;
  /** Идентификатор смотрящего: его строка помечается. */
  selfId: string | null;
  /** Отказ смены роли или удаления. */
  failure?: Failure | null;
  /** Отказ добавления. */
  addFailure?: Failure | null;
  adding?: boolean;
  /** Строка, над которой идёт запрос. */
  busyUserId?: string | null;
  removing?: boolean;
  onRetry?: () => void;
  /** Результат true очищает форму; при отказе она остаётся как есть. */
  onAdd: (email: string, role: OrgRoleName) => Promise<boolean> | undefined;
  onSetRole: (member: AdminOrgMember, role: OrgRoleName) => void;
  onRemove: (member: AdminOrgMember) => Promise<boolean> | undefined;
  /** Сбросить отказы при новом действии. */
  onReset?: () => void;
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Вкладка «Участники»: добавление по почте, смена роли, удаление, защита последнего владельца. */
export const MembersView = ({
  status,
  members,
  viewer,
  selfId,
  failure = null,
  addFailure = null,
  adding = false,
  busyUserId = null,
  removing = false,
  onRetry,
  onAdd,
  onSetRole,
  onRemove,
  onReset,
}: MembersViewProps) => {
  const { t, i18n } = useTranslation("adminOrgs");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRoleName>("member");
  const [tried, setTried] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [confirming, setConfirming] = useState<AdminOrgMember | null>(null);

  const roles = assignableRoles(viewer);
  const roleOptions = (list: readonly OrgRoleName[]) =>
    list.map((r) => ({ value: r, label: t(`role.${r}`) }));

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return members.filter(
      (m) =>
        (roleFilter === "" || m.role === roleFilter) &&
        (needle === "" ||
          m.name.toLowerCase().includes(needle) ||
          m.email.toLowerCase().includes(needle)),
    );
  }, [members, search, roleFilter]);

  const emailError =
    tried && !EMAIL.test(email.trim())
      ? t("members.add.emailInvalid")
      : undefined;

  const submitAdd = async () => {
    setTried(true);
    onReset?.();
    if (!EMAIL.test(email.trim())) return;
    const ok = await onAdd(email.trim(), role);
    if (ok) {
      setEmail("");
      setTried(false);
      setRole("member");
      setAddOpen(false);
    }
  };

  const closeAdd = () => {
    if (adding) return;
    setAddOpen(false);
    setEmail("");
    setTried(false);
    setRole("member");
    onReset?.();
  };

  const columns: ColumnDef<AdminOrgMember>[] = [
    {
      id: "person",
      header: t("members.columns.person"),
      cell: ({ row }) => (
        <PersonCell
          name={row.original.name}
          email={row.original.email}
          id={row.original.user_id}
          badges={
            row.original.user_id === selfId ? (
              <Badge variant="subtle" data-testid="member-self">
                {t("members.you")}
              </Badge>
            ) : null
          }
        />
      ),
    },
    {
      id: "role",
      header: t("members.columns.role"),
      cell: ({ row }) => {
        const m = row.original;
        if (isLastOwner(members, m)) {
          return (
            <Tooltip content={t("members.lastOwner")}>
              <span
                className="org-lock"
                tabIndex={0}
                data-testid={`member-last-owner-${m.user_id}`}
              >
                <span className="org-role-text">{t(`role.${m.role}`)}</span>
                <Lock
                  size={12}
                  aria-hidden="true"
                  style={{ color: "var(--fg-3)" }}
                />
                <span className="sr-only">{t("members.lastOwner")}</span>
              </span>
            </Tooltip>
          );
        }
        // В таблице роль текстом, как у соседних ячеек; выбор проявляется при наведении.
        if (!canEditMember(viewer, m.role)) {
          return (
            <span className="org-role-text" data-testid={`role-${m.role}`}>
              {t(`role.${m.role}`)}
            </span>
          );
        }
        return (
          <div
            className="org-role-select"
            data-testid={`member-role-${m.user_id}`}
          >
            <Select
              value={m.role}
              placeholder={t("members.roleFor", { name: m.name })}
              isDisabled={busyUserId === m.user_id}
              options={roleOptions(roles)}
              onValueChange={(next) => {
                onSetRole(m, next as OrgRoleName);
              }}
            />
          </div>
        );
      },
    },
    {
      id: "joined",
      header: t("members.columns.joined"),
      cell: ({ row }) => (
        <time
          className="org-muted"
          dateTime={row.original.joined_at}
          title={formatDate(row.original.joined_at, i18n.language)}
          style={{ whiteSpace: "nowrap" }}
        >
          {formatPastTime(row.original.joined_at)}
        </time>
      ),
    },
    {
      id: "actions",
      header: () => (
        <span className="sr-only">{t("members.columns.actions")}</span>
      ),
      cell: ({ row }) => {
        const m = row.original;
        // Единственного владельца и людей с ролью выше своей убрать нельзя:
        // меню у такой строки нет, замок у роли объясняет почему.
        if (isLastOwner(members, m) || !canEditMember(viewer, m.role)) {
          return null;
        }
        return (
          <div className="flex" style={{ justifyContent: "flex-end" }}>
            <ActionMenu
              label={t("members.actions", { name: m.name })}
              testId={`member-actions-${m.user_id}`}
              items={[
                {
                  id: "remove",
                  label: t("members.remove.item"),
                  icon: <UserMinus size={14} aria-hidden="true" />,
                  danger: true,
                  disabled: busyUserId === m.user_id,
                  testId: `member-remove-${m.user_id}`,
                  onSelect: () => {
                    onReset?.();
                    setConfirming(m);
                  },
                },
              ]}
            />
          </div>
        );
      },
    },
  ];

  const counts = (r: OrgRoleName) => members.filter((m) => m.role === r).length;

  return (
    <div className="org-stack" data-testid="members-tab">
      {failure && <FailureNotice failure={failure} />}

      <div className="org-toolbar">
        <FilterBar
          className="org-toolbar-filters"
          search={search}
          onSearchChange={setSearch}
          searchLabel={t("members.search")}
          searchPlaceholder={t("members.search")}
          filters={[
            {
              id: "role",
              label: t("members.columns.role"),
              value: roleFilter,
              onChange: setRoleFilter,
              options: ROLES.map((r) => ({
                value: r,
                label: t(`role.${r}`),
                ...(status === "ready" ? { count: counts(r) } : {}),
              })),
            },
          ]}
          onReset={() => {
            setSearch("");
            setRoleFilter("");
          }}
        />
        <Button
          type="button"
          data-testid="member-add-open"
          onClick={() => {
            onReset?.();
            setAddOpen(true);
          }}
        >
          <UserPlus size={14} aria-hidden="true" />
          {t("members.add.title")}
        </Button>
      </div>
      <DataTable
        className="org-table"
        caption={t("members.caption")}
        columns={columns}
        data={rows}
        getRowId={(m) => m.user_id}
        loading={status === "loading"}
        error={status === "error" ? t("members.loadFailed") : null}
        {...(onRetry ? { onRetry } : {})}
        emptyTitle={
          members.length > 0 ? t("members.noMatch") : t("members.empty.title")
        }
        {...(members.length > 0 ? {} : { emptyHint: t("members.empty.body") })}
      />

      <Modal
        isOpen={addOpen}
        onClose={closeAdd}
        width={440}
        title={t("members.add.title")}
        description={t("members.add.lead")}
        footer={
          <>
            <Button
              variant="ghost"
              type="button"
              disabled={adding}
              onClick={closeAdd}
            >
              {t("cancel")}
            </Button>
            <Button
              type="submit"
              form="member-add-form"
              disabled={adding}
              data-testid="member-add-submit"
            >
              {adding && <Spinner size="sm" />}
              {t("members.add.submit")}
            </Button>
          </>
        }
      >
        <form
          id="member-add-form"
          className="flex flex-col"
          style={{ gap: 14 }}
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void submitAdd();
          }}
          data-testid="member-add-form"
        >
          <Input
            label={t("members.add.email")}
            type="email"
            value={email}
            autoComplete="off"
            placeholder="name@example.org"
            {...(emailError ? { error: emailError } : {})}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
            data-testid="member-add-email"
          />
          <div className="field">
            <label htmlFor="member-add-role">{t("members.add.role")}</label>
            <Select
              id="member-add-role"
              value={role}
              placeholder={t("members.add.role")}
              options={roleOptions(roles)}
              onValueChange={(next) => {
                setRole(next as OrgRoleName);
              }}
            />
          </div>
          {addFailure && (
            <FailureNotice
              failure={
                addFailure.code === "not_found" ||
                addFailure.code === "user_not_found"
                  ? { code: "member_not_found" }
                  : addFailure
              }
            />
          )}
        </form>
      </Modal>

      <Modal
        isOpen={confirming !== null}
        onClose={() => {
          if (!removing) setConfirming(null);
        }}
        title={t("members.remove.title")}
        description={
          confirming
            ? t(
                confirming.user_id === selfId
                  ? "members.remove.bodySelf"
                  : "members.remove.body",
                { name: confirming.name },
              )
            : undefined
        }
        footer={
          <>
            <Button
              variant="ghost"
              type="button"
              disabled={removing}
              onClick={() => {
                setConfirming(null);
              }}
            >
              {t("cancel")}
            </Button>
            <Button
              variant="danger"
              type="button"
              disabled={removing}
              data-testid="member-remove-confirm"
              onClick={() => {
                if (!confirming) return;
                void Promise.resolve(onRemove(confirming)).then(() => {
                  setConfirming(null);
                });
              }}
            >
              {removing && <Spinner size="sm" />}
              {t("members.remove.confirm")}
            </Button>
          </>
        }
      />
    </div>
  );
};
