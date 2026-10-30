import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, FilterBar, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminAuditEvent } from "@entities/session";
import { useAudit } from "../api/adminUsersQueries";
import { detailText, formatDateTime } from "../lib/format";
import { HINT } from "../lib/styles";

const GROUPS = [
  "auth.",
  "admin.",
  "invite.",
  "org.",
  "group.",
  "settings.",
  "runner.",
  "project.",
] as const;

const DETAIL_LIMIT = 4;

const shortId = (id: string): string =>
  id.length > 12 ? `${id.slice(0, 10)}…` : id;

const Details = ({ details }: { details: Record<string, unknown> }) => {
  const entries = Object.entries(details)
    .map(([key, value]) => [key, detailText(value)] as const)
    .filter(([, value]) => value !== "")
    .slice(0, DETAIL_LIMIT);
  if (entries.length === 0) return null;
  return (
    <span
      className="mono"
      style={{ fontSize: 11, color: "var(--fg-2)", overflowWrap: "anywhere" }}
    >
      {entries.map(([key, value]) => `${key}: ${value}`).join(" · ")}
    </span>
  );
};

/** Раздел «Аудит»: журнал действий, новые сверху, дальше подгружается по кнопке. */
export const AuditLog = () => {
  const { t, i18n } = useTranslation("adminUsers");
  const [group, setGroup] = useState("");
  const audit = useAudit(group);
  const [search, setSearch] = useState("");
  const label = (action: string): string => {
    const key = "audit.actions." + action.replaceAll(".", "_");
    return i18n.exists(key, { ns: "adminUsers" }) ? t(key) : action;
  };
  const all = useMemo<AdminAuditEvent[]>(
    () => audit.data?.pages.flatMap((p) => p.items) ?? [],
    [audit.data],
  );
  const filtering = group !== "" || search.trim() !== "";
  // Поиск идёт по уже загруженным записям: подпись, код действия, кто, на что и подробности.
  const events = all.filter((e) => {
    const needle = search.trim().toLowerCase();
    if (needle === "") return true;
    const hay = [
      label(e.action),
      e.action,
      e.actor_id ?? "",
      e.target ?? "",
      ...Object.values(e.details).map(detailText),
    ];
    return hay.some((part) => part.toLowerCase().includes(needle));
  });

  return (
    <div className="flex flex-col" style={{ gap: 14 }} data-testid="audit-log">
      <header className="flex flex-col" style={{ gap: 4 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
          {t("audit.title")}
        </h1>
        <p style={{ margin: 0, fontSize: 13, color: "var(--fg-2)" }}>
          {t("audit.lead")}
        </p>
      </header>
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        searchLabel={t("audit.search")}
        searchPlaceholder={t("audit.search")}
        filters={[
          {
            id: "group",
            label: t("audit.group"),
            value: group,
            onChange: setGroup,
            options: GROUPS.map((g) => ({
              value: g,
              label: t(`audit.groups.${g.slice(0, -1)}`),
            })),
          },
        ]}
        onReset={() => {
          setGroup("");
          setSearch("");
        }}
      />
      {audit.isError && (
        <Notice
          tone="err"
          role="alert"
          text={t("audit.loadFailed")}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void audit.refetch();
              }}
            >
              {t("retry")}
            </button>
          }
        />
      )}
      {audit.isPending && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          role="status"
        >
          <Spinner size="sm" />
          <span className="dim">{t("loading")}</span>
        </div>
      )}
      {!audit.isPending && !audit.isError && events.length === 0 && (
        <div
          className="flex flex-col"
          style={{
            gap: 6,
            padding: 20,
            border: "1px dashed var(--border)",
            borderRadius: "var(--r-2)",
          }}
          data-testid="audit-empty"
        >
          <strong style={{ fontSize: 13 }}>
            {t(filtering ? "audit.noMatch.title" : "audit.empty.title")}
          </strong>
          <span style={HINT}>
            {t(filtering ? "audit.noMatch.body" : "audit.empty.body")}
          </span>
        </div>
      )}
      {events.length > 0 && (
        <ul
          aria-label={t("audit.caption")}
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            border: "1px solid var(--border)",
            borderRadius: "var(--r-3)",
            background: "var(--bg-1)",
            overflow: "hidden",
          }}
        >
          {events.map((e) => (
            <li
              key={e.id}
              className="flex flex-col"
              data-testid={"audit-" + String(e.id)}
              style={{
                gap: 2,
                padding: "10px 14px",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <span
                className="flex items-baseline"
                style={{ gap: 10, flexWrap: "wrap" }}
              >
                <span style={{ fontWeight: 500, fontSize: 13 }}>
                  {label(e.action)}
                </span>
                <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                  {formatDateTime(e.at, i18n.language)}
                </span>
              </span>
              <span
                className="mono"
                style={{ fontSize: 11, color: "var(--fg-2)" }}
              >
                {e.action}
                {" · "}
                {e.actor_id
                  ? t("audit.by", { id: shortId(e.actor_id) })
                  : t("audit.system")}
                {e.target ? ` → ${shortId(e.target)}` : ""}
              </span>
              <Details details={e.details} />
            </li>
          ))}
        </ul>
      )}
      {audit.hasNextPage && (
        <div>
          <Button
            variant="outline"
            type="button"
            disabled={audit.isFetchingNextPage}
            data-testid="audit-more"
            onClick={() => {
              void audit.fetchNextPage();
            }}
          >
            {audit.isFetchingNextPage && <Spinner size="sm" />}
            {t("audit.more")}
          </Button>
        </div>
      )}
    </div>
  );
};
