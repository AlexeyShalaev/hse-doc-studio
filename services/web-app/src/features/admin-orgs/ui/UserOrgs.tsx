import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Pagination, SearchInput } from "@shared/ui";
import { adminOrgsApi } from "../api/adminOrgsApi";
import { adminOrgsKeys } from "../api/adminOrgsQueries";
import { OrgMark } from "./parts";

// В карточке места мало: короткие страницы, поиск появляется, когда
// организаций больше одной страницы.
const PAGE = 10;

/**
 * В каких организациях состоит человек и с какой ролью: одна ручка сервера
 * (/users/{id}/orgs) с поиском и страницами, без обхода составов организаций.
 * Поиск и страница живут в карточке, а не в адресе: адрес принадлежит списку людей.
 */
export const UserOrgs = ({ userId }: { userId: string }) => {
  const { t } = useTranslation("adminOrgs");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const params = { limit: PAGE, offset: page * PAGE, ...(q ? { q } : {}) };
  const orgs = useQuery({
    queryKey: [...adminOrgsKeys.userOrgs(userId), params],
    queryFn: ({ signal }) => adminOrgsApi.userOrgs(userId, params, signal),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });

  const total = orgs.data?.total ?? 0;
  const rows = orgs.data?.items ?? [];
  const searchable = q !== "" || total > PAGE;

  if (orgs.isPending) {
    return (
      <div className="flex flex-col" style={{ gap: 8 }} aria-hidden="true">
        <span className="adm-skel" style={{ width: "60%" }} />
        <span className="adm-skel" style={{ width: "45%" }} />
      </div>
    );
  }
  if (orgs.isError && rows.length === 0) {
    return (
      <p className="org-muted" style={{ margin: 0, fontSize: 12.5 }}>
        {t("userOrgs.failed")}
      </p>
    );
  }
  return (
    <div className="flex flex-col" style={{ gap: 8 }}>
      {searchable && (
        <SearchInput
          value={q}
          onChange={(next) => {
            setQ(next);
            setPage(0);
          }}
          busy={orgs.isFetching}
          label={t("userOrgs.search")}
          placeholder={t("userOrgs.search")}
          testId="user-orgs-search"
        />
      )}
      {rows.length === 0 ? (
        <p className="org-muted" style={{ margin: 0, fontSize: 12.5 }}>
          {q ? t("userOrgs.noMatch") : t("userOrgs.none")}
        </p>
      ) : (
        <ul
          className="org-user-orgs"
          data-testid="user-orgs"
          style={{ opacity: orgs.isPlaceholderData ? 0.6 : 1 }}
        >
          {rows.map((org) => (
            <li key={org.slug}>
              <Link to={`/admin/orgs/${encodeURIComponent(org.slug)}`}>
                <OrgMark name={org.name} slug={org.slug} size={22} />
                <span className="org-user-orgs-name">{org.name}</span>
              </Link>
              <span className="org-role-text">{t(`role.${org.role}`)}</span>
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
          busy={orgs.isFetching}
        />
      )}
    </div>
  );
};
