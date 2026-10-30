import { useState } from "react";
import { useSearchParams } from "react-router";
import { ApiError, failureCode } from "@shared/api";
import { useBootstrap } from "@entities/session";
import { useDeleteOrg, useGroupCount, useOrg } from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
import { GROUPS_LIST, MEMBERS_LIST } from "../lib/listState";
import type { Viewer } from "../lib/permissions";
import { GroupsTab } from "./GroupsTab";
import { MembersTab } from "./MembersTab";
import { OrgDetailView, type OrgTab } from "./OrgDetailView";

const TABS: readonly OrgTab[] = ["members", "groups", "settings"];
const MEMBERS_PREFIX = MEMBERS_LIST.prefix ?? "m.";
const GROUPS_PREFIX = GROUPS_LIST.prefix ?? "g.";

const isTab = (value: string | null): value is OrgTab =>
  TABS.includes(value as OrgTab);

const hasPrefix = (params: URLSearchParams, prefix: string): boolean =>
  [...params.keys()].some((key) => key.startsWith(prefix));

/**
 * Вкладка по адресу: явный ?tab=…, иначе по приставке ключей списка
 * (ссылка с ?g.page=2 открывает группы), иначе вкладка по умолчанию.
 */
const orgTabFromParams = (
  params: URLSearchParams,
  fallback: OrgTab,
): OrgTab => {
  const fromUrl = params.get("tab");
  if (isTab(fromUrl)) return fromUrl;
  if (hasPrefix(params, GROUPS_PREFIX)) return "groups";
  if (hasPrefix(params, MEMBERS_PREFIX)) return "members";
  return fallback;
};

/** Организация по адресу: шапка, вкладки участников, групп, проектов и настроек. */
export const OrgDetail = ({
  slug,
  initialTab = "members",
  onBack,
  onDeleted,
}: {
  slug: string;
  initialTab?: OrgTab;
  onBack: () => void;
  onDeleted: () => void;
}) => {
  const org = useOrg(slug);
  // Число групп на вкладке: total ответа из одной строки, без всего списка.
  const groupCount = useGroupCount(slug).data ?? null;
  const remove = useDeleteOrg();
  const user = useBootstrap().data?.user;
  // Вкладка в адресе, как у пользователей и раннеров: перезагрузка, ссылка
  // и «Назад» открывают тот же вид. Условия другой вкладки при смене
  // стираются, свои остаются.
  const [params, setParams] = useSearchParams();
  const tab = orgTabFromParams(params, initialTab);
  const setTab = (next: OrgTab) => {
    if (next === tab) return;
    const keep = next === "groups" ? GROUPS_PREFIX : MEMBERS_PREFIX;
    const nextParams = new URLSearchParams();
    for (const [key, value] of params) {
      if (key === "tab") continue;
      const listKey =
        key.startsWith(MEMBERS_PREFIX) || key.startsWith(GROUPS_PREFIX);
      if (listKey && (next === "settings" || !key.startsWith(keep))) continue;
      nextParams.append(key, value);
    }
    if (next !== "members") nextParams.set("tab", next);
    setParams(nextParams);
  };
  const [deleteFailure, setDeleteFailure] = useState<Failure | null>(null);

  const instanceAdmin = user?.is_instance_admin === true;
  const viewer: Viewer = {
    instanceAdmin,
    role: org.data?.my_role ?? null,
  };
  // Чужая и несуществующая организации выглядят одинаково: 404.
  const missing = org.error instanceof ApiError && org.error.status === 404;
  const status = org.data
    ? "ready"
    : missing
      ? "missing"
      : org.isError
        ? "error"
        : "loading";

  return (
    <OrgDetailView
      status={status}
      org={org.data ?? null}
      tab={tab}
      onTab={setTab}
      onBack={onBack}
      onRetry={() => {
        void org.refetch();
      }}
      groupCount={groupCount}
      canDelete={instanceAdmin}
      deleting={remove.isPending}
      deleteFailure={deleteFailure}
      onDeleteReset={() => {
        setDeleteFailure(null);
      }}
      onDelete={() => {
        setDeleteFailure(null);
        remove.mutate(slug, {
          onSuccess: onDeleted,
          onError: (error) => {
            setDeleteFailure({ code: failureCode(error) });
          },
        });
      }}
    >
      {tab === "members" && (
        <MembersTab slug={slug} viewer={viewer} selfId={user?.id ?? null} />
      )}
      {tab === "groups" && <GroupsTab slug={slug} />}
    </OrgDetailView>
  );
};
