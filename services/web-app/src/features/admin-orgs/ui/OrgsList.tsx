import { useState } from "react";
import { useBootstrap } from "@entities/session";
import { useOrgs } from "../api/adminOrgsQueries";
import { canCreateOrg } from "../lib/permissions";
import { CreateOrgModal } from "./CreateOrgModal";
import { OrgsListView } from "./OrgsListView";

/** Раздел «Организации»: список организаций, видимых смотрящему, и создание новой. */
export const OrgsList = ({ onOpen }: { onOpen: (slug: string) => void }) => {
  const orgs = useOrgs();
  const user = useBootstrap().data?.user;
  const [creating, setCreating] = useState(false);
  const canCreate = canCreateOrg({
    instanceAdmin: user?.is_instance_admin === true,
  });

  const status = orgs.isError ? "error" : orgs.isPending ? "loading" : "ready";
  return (
    <>
      <OrgsListView
        status={status}
        orgs={orgs.data ?? []}
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
