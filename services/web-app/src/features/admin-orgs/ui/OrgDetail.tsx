import { useState } from "react";
import { ApiError, failureCode } from "@shared/api";
import { useBootstrap } from "@entities/session";
import { useDeleteOrg, useGroupCount, useOrg } from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
import type { Viewer } from "../lib/permissions";
import { GroupsTab } from "./GroupsTab";
import { MembersTab } from "./MembersTab";
import { OrgDetailView, type OrgTab } from "./OrgDetailView";

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
  const [tab, setTab] = useState<OrgTab>(initialTab);
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
