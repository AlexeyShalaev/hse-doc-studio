import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import type { PickerItem } from "@shared/lib";
import {
  Avatar,
  Button,
  Input,
  Pagination,
  Picker,
  SearchInput,
  Spinner,
  type PickerSource,
} from "@shared/ui";
import type { AdminGroup } from "@entities/session";
import { adminOrgsApi } from "../api/adminOrgsApi";
import { adminOrgsKeys, useGroupMembership } from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
import { FailureNotice } from "./parts";

export type GroupDraft = { name: string; memberIds: string[] };

// Состав группы в окне листается страницами по 10 и ищется на сервере:
// в группе могут быть сотни людей. Участников ищет пикер по составу
// организации, а не список «всех загруженных».
const PAGE = 10;

/**
 * Форма группы. Новая: название и первые участники из пикера, всё уходит
 * одним запросом. Существующая: название сохраняется кнопкой, а состав
 * меняется сразу, по одному человеку (POST и DELETE .../members/{id}).
 */
export const GroupForm = ({
  slug,
  source,
  initial,
  saving,
  failure,
  onCancel,
  onSubmit,
}: {
  /** Организация; без неё (галерея) состав существующей группы не грузится. */
  slug: string | null;
  /** Поиск участников организации; без него выбирать некого. */
  source: PickerSource | null;
  initial: AdminGroup | null;
  saving: boolean;
  failure: Failure | null;
  onCancel: () => void;
  onSubmit: (draft: GroupDraft) => Promise<void>;
}) => {
  const { t } = useTranslation("adminOrgs");
  const [name, setName] = useState(initial?.name ?? "");
  const [chosen, setChosen] = useState<PickerItem[]>([]);
  const [tried, setTried] = useState(false);

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
        void onSubmit({
          name: name.trim(),
          memberIds: chosen.map((p) => p.id),
        });
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
      {initial && slug ? (
        <GroupMembers slug={slug} group={initial} source={source} />
      ) : (
        <fieldset
          className="flex flex-col"
          style={{ gap: 8, border: 0, margin: 0, padding: 0, minWidth: 0 }}
        >
          <legend className="org-legend">
            {t("groups.form.members", { count: chosen.length })}
          </legend>
          {source === null ? (
            <p className="org-muted" style={{ margin: 0, fontSize: 12 }}>
              {t("groups.form.noMembers")}
            </p>
          ) : (
            <Picker
              source={source}
              value={null}
              onChange={(item) => {
                if (item && !chosen.some((p) => p.id === item.id))
                  setChosen([...chosen, item]);
              }}
              label={t("groups.form.add")}
              placeholder={t("groups.form.add")}
              searchPlaceholder={t("groups.form.search")}
              emptyText={t("groups.form.noMatch")}
              testId="group-add-person"
            />
          )}
          {chosen.length > 0 && (
            <ul className="org-chosen" data-testid="group-chosen">
              {chosen.map((p) => (
                <li key={p.id}>
                  <Avatar name={p.name} seed={p.id} size={20} />
                  <span>{p.name}</span>
                  <button
                    type="button"
                    className="org-chosen-remove"
                    aria-label={t("groups.form.unpick", { name: p.name })}
                    onClick={() => {
                      setChosen(chosen.filter((x) => x.id !== p.id));
                    }}
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
      )}
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

/** Состав существующей группы: поиск, страницы, добавить и убрать сразу. */
const GroupMembers = ({
  slug,
  group,
  source,
}: {
  slug: string;
  group: AdminGroup;
  source: PickerSource | null;
}) => {
  const { t } = useTranslation("adminOrgs");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [failure, setFailure] = useState<Failure | null>(null);
  const params = {
    limit: PAGE,
    offset: page * PAGE,
    sort: "name",
    ...(q ? { q } : {}),
  };
  const members = useQuery({
    queryKey: [...adminOrgsKeys.groupMembers(slug, group.id), params],
    queryFn: ({ signal }) =>
      adminOrgsApi.groupMembers(slug, group.id, params, signal),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
  const change = useGroupMembership(slug, group.id);
  const total = members.data?.total ?? 0;
  const rows = members.data?.items ?? [];
  const busyId = change.isPending ? change.variables.userId : null;

  const apply = (userId: string, add: boolean) => {
    setFailure(null);
    change.mutate(
      { userId, add },
      {
        onError: (error) => {
          setFailure({ code: failureCode(error) });
        },
      },
    );
  };

  return (
    <fieldset
      className="flex flex-col"
      style={{ gap: 8, border: 0, margin: 0, padding: 0, minWidth: 0 }}
      data-testid="group-members"
    >
      <legend className="org-legend">
        {t("groups.form.members", { count: total })}
      </legend>
      {source && (
        <Picker
          source={source}
          value={null}
          onChange={(item) => {
            if (item) apply(item.id, true);
          }}
          label={t("groups.form.add")}
          placeholder={t("groups.form.add")}
          searchPlaceholder={t("groups.form.search")}
          emptyText={t("groups.form.noMatch")}
          disabled={change.isPending}
          testId="group-add-person"
        />
      )}
      {(q !== "" || total > PAGE) && (
        <SearchInput
          value={q}
          onChange={(next) => {
            setQ(next);
            setPage(0);
          }}
          busy={members.isFetching}
          label={t("groups.form.searchIn")}
          placeholder={t("groups.form.searchIn")}
        />
      )}
      {failure && <FailureNotice failure={failure} />}
      {members.isPending ? (
        <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          <span className="org-muted">{t("loading")}</span>
        </div>
      ) : members.isError && rows.length === 0 ? (
        <p className="org-muted" style={{ margin: 0, fontSize: 12 }}>
          {t("groups.form.loadFailed")}
        </p>
      ) : rows.length === 0 ? (
        <p className="org-muted" style={{ margin: 0, fontSize: 12 }}>
          {q ? t("groups.form.noMatch") : t("groups.noPeople")}
        </p>
      ) : (
        <ul
          className="org-picker"
          style={{ opacity: members.isPlaceholderData ? 0.6 : 1 }}
        >
          {rows.map((m) => (
            <li key={m.user_id} className="org-member-row">
              <Avatar name={m.name} seed={m.user_id} size={24} />
              <span className="flex flex-col" style={{ minWidth: 0, flex: 1 }}>
                <span style={{ fontSize: 12.5 }}>{m.name}</span>
                <span style={{ fontSize: 11, color: "var(--fg-2)" }}>
                  {m.email}
                </span>
              </span>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                disabled={busyId !== null}
                aria-label={t("groups.form.removeOne", { name: m.name })}
                title={t("groups.form.removeOne", { name: m.name })}
                data-testid={`group-member-remove-${m.user_id}`}
                onClick={() => {
                  apply(m.user_id, false);
                }}
              >
                {busyId === m.user_id ? (
                  <Spinner size="sm" />
                ) : (
                  <X size={13} aria-hidden="true" />
                )}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {total > PAGE && (
        <Pagination
          page={page}
          pageSize={PAGE}
          total={total}
          onPageChange={setPage}
          busy={members.isFetching}
        />
      )}
    </fieldset>
  );
};
