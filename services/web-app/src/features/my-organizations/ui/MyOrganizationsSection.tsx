import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { useBootstrap, type MyOrg } from "@entities/session";
import { useLeaveOrg, useMyOrgs } from "../api/myOrgsQueries";
import type { Failure } from "../lib/failure";
import { MyOrganizationsView } from "./MyOrganizationsView";

/** Раздел настроек «Организации» серверного режима. */
export const MyOrganizationsSection = () => {
  const { t } = useTranslation("organizations");
  const orgs = useMyOrgs();
  const leave = useLeaveOrg();
  const instanceAdmin = useBootstrap().data?.user?.is_instance_admin === true;
  const [failure, setFailure] = useState<Failure | null>(null);
  const [leavingSlug, setLeavingSlug] = useState<string | null>(null);

  const onLeave = (org: MyOrg) => {
    setFailure(null);
    setLeavingSlug(org.slug);
    leave.mutate(org.slug, {
      onSuccess: () => {
        toast.success(t("leave.done", { name: org.name }));
      },
      onError: (error: unknown) => {
        setFailure({ code: failureCode(error) });
      },
      onSettled: () => {
        setLeavingSlug(null);
      },
    });
  };

  return (
    <MyOrganizationsView
      status={orgs.data ? "ready" : orgs.isError ? "error" : "loading"}
      orgs={orgs.data ?? []}
      failure={failure}
      leavingSlug={leavingSlug}
      instanceAdmin={instanceAdmin}
      onRetry={() => {
        void orgs.refetch();
      }}
      onLeave={onLeave}
      onReset={() => {
        setFailure(null);
      }}
    />
  );
};
