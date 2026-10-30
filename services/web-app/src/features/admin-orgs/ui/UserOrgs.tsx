import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { adminOrgsApi } from "../api/adminOrgsApi";
import { adminOrgsKeys } from "../api/adminOrgsQueries";
import { OrgMark } from "./parts";

/**
 * В каких организациях состоит человек и с какой ролью: один запрос
 * `GET /api/admin/users/{id}/orgs`, а не составы всех организаций установки.
 */
export const UserOrgs = ({ userId }: { userId: string }) => {
  const { t } = useTranslation("adminOrgs");
  const orgs = useQuery({
    queryKey: adminOrgsKeys.userOrgs(userId),
    queryFn: () => adminOrgsApi.userOrgs(userId),
    staleTime: 30_000,
  });

  const loading = orgs.isPending;
  const failed = orgs.isError;
  const rows = (orgs.data?.items ?? []).map((org) => ({ org, role: org.role }));

  if (loading) {
    return (
      <div className="flex flex-col" style={{ gap: 8 }} aria-hidden="true">
        <span className="adm-skel" style={{ width: "60%" }} />
        <span className="adm-skel" style={{ width: "45%" }} />
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <p className="org-muted" style={{ margin: 0, fontSize: 12.5 }}>
        {failed ? t("userOrgs.failed") : t("userOrgs.none")}
      </p>
    );
  }
  return (
    <ul className="org-user-orgs" data-testid="user-orgs">
      {rows.map(({ org, role }) => (
        <li key={org.slug}>
          <Link to={`/admin/orgs/${encodeURIComponent(org.slug)}`}>
            <OrgMark name={org.name} slug={org.slug} size={22} />
            <span className="org-user-orgs-name">{org.name}</span>
          </Link>
          <span className="org-role-text">{t(`role.${role}`)}</span>
        </li>
      ))}
    </ul>
  );
};
