import { useState } from "react";
import { Pencil, Plus, Trash2, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Modal, Spinner } from "@shared/ui";
import type { AdminGroup, AdminOrgMember } from "@entities/session";
import type { Failure } from "../lib/failure";
import { CARD } from "../lib/styles";
import {
  Avatar,
  EmptyBlock,
  FailureNotice,
  LoadFailed,
  LoadingRow,
} from "./parts";

export type GroupDraft = { name: string; memberIds: string[] };

export type GroupsViewProps = {
  status: "loading" | "error" | "ready";
  groups: readonly AdminGroup[];
  members: readonly AdminOrgMember[];
  /** Отказ последнего сохранения формы. */
  formFailure?: Failure | null;
  /** Отказ удаления. */
  failure?: Failure | null;
  saving?: boolean;
  deleting?: boolean;
  onRetry?: () => void;
  /** Результат true закрывает форму; при отказе она остаётся открытой. */
  onCreate: (draft: GroupDraft) => Promise<boolean> | undefined;
  onUpdate: (
    group: AdminGroup,
    draft: GroupDraft,
  ) => Promise<boolean> | undefined;
  onDelete: (group: AdminGroup) => Promise<boolean> | undefined;
  onReset?: () => void;
};

const SHOWN_AVATARS = 5;

/** Вкладка «Группы»: карточки групп, создание, правка состава, удаление. */
export const GroupsView = ({
  status,
  groups,
  members,
  formFailure = null,
  failure = null,
  saving = false,
  deleting = false,
  onRetry,
  onCreate,
  onUpdate,
  onDelete,
  onReset,
}: GroupsViewProps) => {
  const { t } = useTranslation("adminOrgs");
  const [form, setForm] = useState<
    { mode: "create" } | { mode: "edit"; group: AdminGroup } | null
  >(null);
  const [removing, setRemoving] = useState<AdminGroup | null>(null);

  const open = (next: NonNullable<typeof form>) => {
    onReset?.();
    setForm(next);
  };
  const byId = new Map(members.map((m) => [m.user_id, m]));

  const addButton = (
    <Button
      size="sm"
      type="button"
      style={{ gap: 6 }}
      onClick={() => {
        open({ mode: "create" });
      }}
      data-testid="group-add"
    >
      <Plus size={14} aria-hidden="true" />
      {t("groups.add")}
    </Button>
  );

  return (
    <div className="flex flex-col" style={{ gap: 14 }} data-testid="groups-tab">
      <div className="flex items-start" style={{ gap: 12 }}>
        <p
          style={{
            margin: 0,
            fontSize: 12.5,
            color: "var(--fg-2)",
            flex: 1,
            maxWidth: 560,
          }}
        >
          {t("groups.lead")}
        </p>
        {status === "ready" && groups.length > 0 && addButton}
      </div>
      {failure && <FailureNotice failure={failure} />}
      {status === "loading" && <LoadingRow testId="groups-loading" />}
      {status === "error" && (
        <LoadFailed text={t("groups.loadFailed")} onRetry={onRetry} />
      )}
      {status === "ready" && groups.length === 0 && (
        <EmptyBlock
          testId="groups-empty"
          icon={<UsersRound size={18} aria-hidden="true" />}
          title={t("groups.empty.title")}
          body={t("groups.empty.body")}
          action={addButton}
        />
      )}
      {status === "ready" && groups.length > 0 && (
        <ul
          aria-label={t("groups.caption")}
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          }}
        >
          {groups.map((group) => {
            const people = group.member_ids
              .map((id) => byId.get(id))
              .filter((m): m is AdminOrgMember => m !== undefined);
            return (
              <li
                key={group.id}
                className="flex flex-col"
                style={{ ...CARD, gap: 12, padding: 14 }}
                data-testid={`group-${group.id}`}
              >
                <div className="flex items-start" style={{ gap: 8 }}>
                  <div
                    className="flex flex-col"
                    style={{ gap: 2, flex: 1, minWidth: 0 }}
                  >
                    <strong style={{ fontSize: 13.5 }}>{group.name}</strong>
                    <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                      {t("groups.count", { count: people.length })}
                    </span>
                  </div>
                  <Button
                    size="xs"
                    variant="ghost"
                    type="button"
                    aria-label={t("groups.edit.aria", { name: group.name })}
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
                    data-testid={`group-delete-${group.id}`}
                    onClick={() => {
                      onReset?.();
                      setRemoving(group);
                    }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </Button>
                </div>
                {people.length === 0 ? (
                  <span style={{ fontSize: 12, color: "var(--fg-3)" }}>
                    {t("groups.noPeople")}
                  </span>
                ) : (
                  <div className="flex items-center" style={{ gap: 0 }}>
                    {people.slice(0, SHOWN_AVATARS).map((m, index) => (
                      <span
                        key={m.user_id}
                        title={m.name}
                        style={{ marginLeft: index === 0 ? 0 : -6 }}
                      >
                        <Avatar
                          name={m.name}
                          size={26}
                          style={{ border: "2px solid var(--bg-1)" }}
                        />
                      </span>
                    ))}
                    {people.length > SHOWN_AVATARS && (
                      <span
                        style={{
                          marginLeft: 8,
                          fontSize: 11.5,
                          color: "var(--fg-2)",
                        }}
                      >
                        {t("groups.more", {
                          count: people.length - SHOWN_AVATARS,
                        })}
                      </span>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
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
            members={members}
            initial={form.mode === "edit" ? form.group : null}
            saving={saving}
            failure={formFailure}
            onCancel={() => {
              setForm(null);
            }}
            onSubmit={async (draft) => {
              const ok =
                form.mode === "edit"
                  ? await onUpdate(form.group, draft)
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

const GroupForm = ({
  members,
  initial,
  saving,
  failure,
  onCancel,
  onSubmit,
}: {
  members: readonly AdminOrgMember[];
  initial: AdminGroup | null;
  saving: boolean;
  failure: Failure | null;
  onCancel: () => void;
  onSubmit: (draft: GroupDraft) => Promise<void>;
}) => {
  const { t } = useTranslation("adminOrgs");
  const [name, setName] = useState(initial?.name ?? "");
  const [chosen, setChosen] = useState<string[]>(initial?.member_ids ?? []);
  const [query, setQuery] = useState("");
  const [tried, setTried] = useState(false);

  const needle = query.trim().toLowerCase();
  const shown = members.filter(
    (m) =>
      needle === "" ||
      m.name.toLowerCase().includes(needle) ||
      m.email.toLowerCase().includes(needle),
  );
  const toggle = (id: string) => {
    setChosen((list) =>
      list.includes(id) ? list.filter((x) => x !== id) : [...list, id],
    );
  };

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      data-testid="group-form"
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (name.trim() === "") return;
        void onSubmit({ name: name.trim(), memberIds: chosen });
      }}
    >
      <Input
        label={t("groups.form.name")}
        value={name}
        maxLength={80}
        autoFocus
        autoComplete="off"
        {...(tried && name.trim() === ""
          ? { error: t("groups.form.nameRequired") }
          : {})}
        onChange={(event) => {
          setName(event.target.value);
        }}
        data-testid="group-name"
      />
      <fieldset
        className="flex flex-col"
        style={{ gap: 8, border: 0, margin: 0, padding: 0, minWidth: 0 }}
      >
        <legend
          style={{ fontSize: 12, fontWeight: 500, padding: 0, marginBottom: 6 }}
        >
          {t("groups.form.members", { count: chosen.length })}
        </legend>
        {members.length === 0 ? (
          <p style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}>
            {t("groups.form.noMembers")}
          </p>
        ) : (
          <>
            <input
              className="input"
              type="search"
              value={query}
              placeholder={t("groups.form.search")}
              aria-label={t("groups.form.search")}
              onChange={(event) => {
                setQuery(event.target.value);
              }}
            />
            <ul
              style={{
                listStyle: "none",
                margin: 0,
                padding: 4,
                maxHeight: 220,
                overflowY: "auto",
                border: "1px solid var(--border)",
                borderRadius: "var(--r-2)",
              }}
            >
              {shown.length === 0 && (
                <li style={{ padding: 8, fontSize: 12, color: "var(--fg-2)" }}>
                  {t("groups.form.noMatch")}
                </li>
              )}
              {shown.map((m) => (
                <li key={m.user_id}>
                  <label
                    className="flex items-center"
                    style={{ gap: 10, padding: "6px 8px", cursor: "pointer" }}
                  >
                    <input
                      type="checkbox"
                      checked={chosen.includes(m.user_id)}
                      onChange={() => {
                        toggle(m.user_id);
                      }}
                      data-testid={`group-member-${m.user_id}`}
                    />
                    <Avatar name={m.name} size={24} />
                    <span className="flex flex-col" style={{ minWidth: 0 }}>
                      <span style={{ fontSize: 12.5 }}>{m.name}</span>
                      <span style={{ fontSize: 11, color: "var(--fg-2)" }}>
                        {m.email}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </>
        )}
      </fieldset>
      {failure && <FailureNotice failure={failure} />}
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={saving}
        >
          {t("cancel")}
        </Button>
        <Button type="submit" disabled={saving} data-testid="group-save">
          {saving && <Spinner size="sm" />}
          {t("save")}
        </Button>
      </div>
    </form>
  );
};
