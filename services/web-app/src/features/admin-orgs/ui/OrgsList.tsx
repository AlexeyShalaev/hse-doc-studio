import { useState } from "react";
import { useListQueryState, useServerList } from "@shared/lib";
import { useBootstrap } from "@entities/session";
import { adminOrgsApi } from "../api/adminOrgsApi";
import { adminOrgsKeys } from "../api/adminOrgsQueries";
import { ORGS_LIST } from "../lib/listState";
import { canCreateOrg } from "../lib/permissions";
import { CreateOrgModal } from "./CreateOrgModal";
import { OrgsListView } from "./OrgsListView";

/** Раздел «Организации»: список организаций, видимых смотрящему, и создание новой. */
export const OrgsList = ({ onOpen }: { onOpen: (slug: string) => void }) => {
  const state = useListQueryState(ORGS_LIST);
  const orgs = useServerList({
    state,
    queryKey: adminOrgsKeys.list(),
    fetchPage: adminOrgsApi.list,
  });
  const user = useBootstrap().data?.user;
  const [creating, setCreating] = useState(false);
  const canCreate = canCreateOrg({
    instanceAdmin: user?.is_instance_admin === true,
  });

  // Сбой опроса при строках на экране не прячет их: ошибку видно, только
  // когда показывать нечего.
  const status =
    orgs.isError && orgs.items.length === 0
      ? "error"
      : orgs.isLoading
        ? "loading"
        : "ready";
  return (
    <>
      <OrgsListView
        status={status}
        orgs={orgs.items}
        total={orgs.isLoading ? null : orgs.total}
        pagination={orgs.pagination}
        fetching={orgs.isFetching}
        canCreate={canCreate}
        onOpen={onOpen}
        onCreate={() => {
          setCreating(true);
        }}
        onRetry={() => {
          void orgs.refetch();
        }}
      />
      <CreateOrgModal
        isOpen={creating}
        onClose={() => {
          setCreating(false);
        }}
        onCreated={onOpen}
      />
    </>
  );
};
