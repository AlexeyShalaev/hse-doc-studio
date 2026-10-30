import { useState } from "react";
import { Pencil, Plus, Trash2, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useListQueryState } from "@shared/lib";
import {
  Avatar,
  Button,
  EmptyState,
  ErrorState,
  FilterBar,
  Modal,
  NoResults,
  Pagination,
  SortSelect,
  Spinner,
  TableSkeleton,
  type DataTablePagination,
  type PickerSource,
} from "@shared/ui";
import type { AdminGroup } from "@entities/session";
import type { Failure } from "../lib/failure";
import { GROUPS_LIST } from "../lib/listState";
import { GroupForm, type GroupDraft } from "./GroupForm";
import { FailureNotice } from "./parts";

export type { GroupDraft } from "./GroupForm";

export type GroupsViewProps = {
  status: "loading" | "error" | "ready";
  /** Группы текущей страницы: поиск и порядок задал сервер. */
  groups: readonly AdminGroup[];
  /** Организация: по ней форма листает состав группы. */
  slug?: string | null;
  /** Поиск участников организации для формы; без него выбирать некого. */
  memberSource?: PickerSource | null;
  total?: number | null;
  pagination?: DataTablePagination;
  fetching?: boolean;
  /** Отказ последнего сохранения формы. */
  formFailure?: Failure | null;
  /** Отказ удаления. */
  failure?: Failure | null;
  saving?: boolean;
  deleting?: boolean;
  onRetry?: () => void;
  /** Результат true закрывает форму; при отказе она остаётся открытой. */
  onCreate: (draft: GroupDraft) => Promise<boolean> | undefined;
  /** Новое название; состав форма меняет сама, по одному человеку. */
  onRename: (group: AdminGroup, name: string) => Promise<boolean> | undefined;
  onDelete: (group: AdminGroup) => Promise<boolean> | undefined;
  onReset?: () => void;
};

/** Вкладка «Группы»: карточки групп, поиск, порядок, страницы, правка и удаление. */
export const GroupsView = ({
  status,
  groups,
  slug = null,
  memberSource = null,
  total = null,
  pagination,
  fetching = false,
  formFailure = null,
  failure = null,
  saving = false,
  deleting = false,
  onRetry,
  onCreate,
  onRename,
  onDelete,
  onReset,
}: GroupsViewProps) => {
  const { t } = useTranslation("adminOrgs");
  const list = useListQueryState(GROUPS_LIST);
  const [form, setForm] = useState<
    { mode: "create" } | { mode: "edit"; group: AdminGroup } | null
  >(null);
  const [removing, setRemoving] = useState<AdminGroup | null>(null);

  const open = (next: NonNullable<typeof form>) => {
    onReset?.();
    setForm(next);
  };

  const addButton = (
    <Button
      size="sm"
      type="button"
      onClick={() => {
        open({ mode: "create" });
      }}
      data-testid="group-add"
    >
      <Plus size={14} aria-hidden="true" />
      {t("groups.add")}
    </Button>
  );

  const empty = status === "ready" && groups.length === 0 && !list.isFiltered;
  const shown = status === "ready" && !empty;

  return (
    <div className="org-stack" data-testid="groups-tab">
      {shown && (
        <>
          <div className="flex items-center" style={{ gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p
                className="org-muted"
                style={{ margin: 0, fontSize: 12.5, maxWidth: 620 }}
              >
                {t("groups.lead")}
              </p>
            </div>
            {addButton}
          </div>
          <FilterBar
            search={list.q}
            onSearchChange={list.setQ}
            searchLabel={t("groups.search")}
            searchPlaceholder={t("groups.search")}
            busy={fetching}
            onReset={list.reset}
            extra={
              <SortSelect
                sort={list.sort}
                onChange={list.setSort}
                label={t("groups.sort.label")}
                testId="groups-sort"
                options={[
                  { field: "name", desc: false, label: t("groups.sort.name") },
                  {
                    field: "member_count",
                    desc: true,
                    label: t("groups.sort.biggest"),
                  },
                  {
                    field: "member_count",
                    desc: false,
                    label: t("groups.sort.smallest"),
                  },
                ]}
              />
            }
          />
        </>
      )}
      {failure && <FailureNotice failure={failure} />}
      {status === "loading" && (
        <TableSkeleton rows={3} columns={2} testId="groups-loading" />
      )}
      {status === "error" && (
        <ErrorState framed title={t("groups.loadFailed")} onRetry={onRetry} />
      )}
      {empty && (
        <EmptyState
          framed
          testId="groups-empty"
          icon={<UsersRound size={18} />}
          title={t("groups.empty.title")}
          description={t("groups.empty.body")}
          action={addButton}
        />
      )}
      {shown && groups.length === 0 && (
        <NoResults framed query={list.q} onReset={list.reset} />
      )}
      {shown && groups.length > 0 && (
        <ul
          aria-label={t("groups.caption")}
          aria-busy={fetching}
          className="org-groups"
          style={{ opacity: fetching ? 0.6 : 1, transition: "opacity 0.12s" }}
        >
          {groups.map((group) => {
            const count = group.member_count;
            const preview = group.preview ?? [];
            return (
              <li
                key={group.id}
                className="org-group"
                data-testid={`group-${group.id}`}
              >
                <div className="org-group-head">
                  <span
                    className="adm-row-icon"
                    aria-hidden="true"
                    style={{ width: 32, height: 32 }}
                  >
                    <UsersRound size={15} />
                  </span>
                  <div
                    className="flex flex-col"
                    style={{ gap: 1, flex: 1, minWidth: 0 }}
                  >
                    <span className="org-group-name">{group.name}</span>
                    <span className="org-muted" style={{ fontSize: 12 }}>
                      {t("groups.count", { count })}
                    </span>
                  </div>
                  <Button
                    size="xs"
                    variant="ghost"
                    type="button"
                    aria-label={t("groups.edit.aria", { name: group.name })}
                    title={t("groups.edit.aria", { name: group.name })}
                    data-testid={`group-edit-${group.id}`}
                    onClick={() => {
                      open({ mode: "edit", group });
                    }}
                  >
                    <Pencil size={13} aria-hidden="true" />
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    type="button"
                    aria-label={t("groups.delete.aria", { name: group.name })}
                    title={t("groups.delete.aria", { name: group.name })}
                    data-testid={`group-delete-${group.id}`}
                    onClick={() => {
                      onReset?.();
                      setRemoving(group);
                    }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </Button>
                </div>
                {count === 0 ? (
                  <span className="org-faint" style={{ fontSize: 12 }}>
                    {t("groups.noPeople")}
                  </span>
                ) : preview.length > 0 ? (
                  <div className="flex items-center" style={{ gap: 10 }}>
                    <span className="org-stack-avatars">
                      {preview.map((m) => (
                        <span key={m.user_id} title={m.name}>
                          <Avatar name={m.name} seed={m.user_id} size={26} />
                        </span>
                      ))}
                    </span>
                    <span className="org-group-names">
                      {count > preview.length
                        ? t("groups.more", { count: count - preview.length })
                        : preview.map((m) => m.name).join(", ")}
                    </span>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {shown && pagination && total !== null && total > 0 && (
        <Pagination {...pagination} />
      )}

      <Modal
        isOpen={form !== null}
        onClose={() => {
          if (!saving) setForm(null);
        }}
        title={
          form?.mode === "edit"
            ? t("groups.form.editTitle")
            : t("groups.form.createTitle")
        }
        width={520}
      >
        {form && (
          <GroupForm
            key={form.mode === "edit" ? form.group.id : "new"}
            slug={slug}
            source={memberSource}
            initial={form.mode === "edit" ? form.group : null}
            saving={saving}
            failure={formFailure}
            onCancel={() => {
              setForm(null);
            }}
            onSubmit={async (draft) => {
              const ok =
                form.mode === "edit"
                  ? await onRename(form.group, draft.name)
                  : await onCreate(draft);
              if (ok) setForm(null);
            }}
          />
        )}
      </Modal>

      <Modal
        isOpen={removing !== null}
        onClose={() => {
          if (!deleting) setRemoving(null);
        }}
        title={t("groups.delete.title")}
        description={
          removing
            ? t("groups.delete.body", { name: removing.name })
            : undefined
        }
        footer={
          <>
            <Button
              variant="ghost"
              type="button"
              disabled={deleting}
              onClick={() => {
                setRemoving(null);
              }}
            >
              {t("cancel")}
            </Button>
            <Button
              variant="danger"
              type="button"
              disabled={deleting}
              data-testid="group-delete-confirm"
              onClick={() => {
                if (!removing) return;
                void Promise.resolve(onDelete(removing)).then(() => {
                  setRemoving(null);
                });
              }}
            >
              {deleting && <Spinner size="sm" />}
              {t("groups.delete.confirm")}
            </Button>
          </>
        }
      />
    </div>
  );
};
