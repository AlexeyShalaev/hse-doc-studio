import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Lock, UserMinus, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  formatPastTime,
  useListQueryState,
  type PickerItem,
} from "@shared/lib";
import {
  ActionMenu,
  Badge,
  Button,
  DataTable,
  FilterBar,
  FilterMenu,
  Input,
  Modal,
  PersonCell,
  Picker,
  Select,
  Spinner,
  Tooltip,
  type ActiveFilter,
  type DataTablePagination,
  type PickerSource,
} from "@shared/ui";
import type { AdminOrgMember, OrgRoleName } from "@entities/session";
import type { AddMemberInput } from "../api/adminOrgsApi";
import type { Failure } from "../lib/failure";
import { formatDate } from "../lib/format";
import { MEMBERS_LIST, MEMBERS_SORTABLE } from "../lib/listState";
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
  /** Строки текущей страницы: поиск, фильтр и порядок задал сервер. */
  members: readonly AdminOrgMember[];
  viewer: Viewer;
  /** Идентификатор смотрящего: его строка помечается. */
  selfId: string | null;
  /** Сколько нашлось при текущих условиях. */
  total?: number | null;
  pagination?: DataTablePagination;
  fetching?: boolean;
  /** Числа на чипах ролей при том же поиске. */
  roleCounts?: Partial<Record<OrgRoleName, number>> | null;
  /** Владельцев в организации: замок у единственного, если строка его не несёт. */
  ownerCount?: number | null;
  /**
   * Поиск людей установки для формы добавления. Есть только у админа
   * установки; админ организации добавляет по почте.
   */
  peopleSource?: PickerSource | null;
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
  onAdd: (input: AddMemberInput) => Promise<boolean> | undefined;
  onSetRole: (member: AdminOrgMember, role: OrgRoleName) => void;
  onRemove: (member: AdminOrgMember) => Promise<boolean> | undefined;
  /** Сбросить отказы при новом действии. */
  onReset?: () => void;
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Вкладка «Участники»: поиск и фильтр на сервере, добавление, смена роли, защита последнего владельца. */
export const MembersView = ({
  status,
  members,
  viewer,
  selfId,
  total = null,
  pagination,
  fetching = false,
  roleCounts = null,
  ownerCount = null,
  peopleSource = null,
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
  const list = useListQueryState(MEMBERS_LIST);
  const roleFilter = list.filters.role as readonly OrgRoleName[];
  const [picked, setPicked] = useState<PickerItem | null>(null);
  // Без пикера (админ организации) остаётся только почта.
  const [byEmail, setByEmail] = useState(peopleSource === null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRoleName>("member");
  const [tried, setTried] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [confirming, setConfirming] = useState<AdminOrgMember | null>(null);

  const roles = assignableRoles(viewer);
  const roleOptions = (list: readonly OrgRoleName[]) =>
    list.map((r) => ({ value: r, label: t(`role.${r}`) }));

  const lastOwner = (m: AdminOrgMember) => isLastOwner(m, ownerCount);

  const emailError =
    tried && byEmail && !EMAIL.test(email.trim())
      ? t("members.add.emailInvalid")
      : undefined;
  const pickError =
    tried && !byEmail && picked === null
      ? t("members.add.personRequired")
      : undefined;

  const clearForm = () => {
    setEmail("");
    setPicked(null);
    setTried(false);
    setRole("member");
    setByEmail(peopleSource === null);
  };

  const submitAdd = async () => {
    setTried(true);
    onReset?.();
    if (byEmail ? !EMAIL.test(email.trim()) : picked === null) return;
    const ok = await onAdd(
      byEmail || picked === null
        ? { email: email.trim(), role }
        : { userId: picked.id, role },
    );
    if (ok) {
      clearForm();
      setAddOpen(false);
    }
  };

  const closeAdd = () => {
    if (adding) return;
    setAddOpen(false);
    clearForm();
    onReset?.();
  };

  const columns: ColumnDef<AdminOrgMember>[] = [
    {
      id: "name",
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
        if (lastOwner(m)) {
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
      id: "joined_at",
      sortDescFirst: true,
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
        if (lastOwner(m) || !canEditMember(viewer, m.role)) {
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

  const active: ActiveFilter[] = [
    ...(list.q
      ? [
          {
            id: "q",
            label: t("members.filters.search"),
            value: list.q,
            onRemove: () => {
              list.setQ("");
            },
          },
        ]
      : []),
    ...(roleFilter.length > 0
      ? [
          {
            id: "role",
            label: t("members.columns.role"),
            value: roleFilter.map((r) => t(`role.${r}`)).join(", "),
            onRemove: () => {
              list.setFilter("role", null);
            },
          },
        ]
      : []),
  ];
  const empty = status === "ready" && members.length === 0 && !list.isFiltered;

  return (
    <div className="org-stack" data-testid="members-tab">
      {failure && <FailureNotice failure={failure} />}

      <div className="org-toolbar">
        <FilterBar
          className="org-toolbar-filters"
          search={list.q}
          onSearchChange={list.setQ}
          searchLabel={t("members.search")}
          searchPlaceholder={t("members.search")}
          busy={fetching}
          onReset={list.reset}
          active={active}
          total={total}
          extra={
            <FilterMenu
              label={t("members.columns.role")}
              testId="members-filter-role"
              values={roleFilter}
              onChange={(values) => {
                list.setFilter("role", values);
              }}
              options={ROLES.map((r) => ({
                value: r,
                label: t(`role.${r}`),
                ...(roleCounts ? { count: roleCounts[r] ?? 0 } : {}),
              }))}
            />
          }
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
        data={[...members]}
        getRowId={(m) => m.user_id}
        loading={status === "loading" || fetching}
        error={status === "error" ? t("members.loadFailed") : null}
        {...(onRetry ? { onRetry } : {})}
        sorting={list.sorting}
        onSortingChange={list.onSortingChange}
        sortable={MEMBERS_SORTABLE}
        filtered={list.isFiltered && !empty}
        searchQuery={list.q}
        onResetFilters={list.reset}
        {...(pagination ? { pagination } : {})}
        emptyTitle={t("members.empty.title")}
        emptyHint={t("members.empty.body")}
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
          {byEmail || peopleSource === null ? (
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
          ) : (
            <div className="field">
              <label htmlFor="member-add-person">
                {t("members.add.person")}
              </label>
              <Picker
                id="member-add-person"
                source={peopleSource}
                value={picked}
                onChange={setPicked}
                label={t("members.add.person")}
                placeholder={t("members.add.personPlaceholder")}
                searchPlaceholder={t("members.add.personSearch")}
                emptyText={t("members.add.personNone")}
                clearable
                testId="member-add-person"
              />
              {pickError && (
                <p className="text-xs text-c-err" role="alert">
                  {pickError}
                </p>
              )}
            </div>
          )}
          {peopleSource !== null && (
            <button
              type="button"
              className="org-link-button"
              data-testid="member-add-mode"
              onClick={() => {
                setByEmail((v) => !v);
                setTried(false);
                onReset?.();
              }}
            >
              {byEmail ? t("members.add.byPicker") : t("members.add.byEmail")}
            </button>
          )}
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
