import { useState } from "react";
import { Building2, Lock, Plus, UserRound, Users, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Input, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  ProjectAccessCandidate,
  ProjectAccessEntry,
  ProjectRole,
} from "@entities/session";
import { useProjectRoleLabel } from "@entities/project";
import { failureKey, type Failure } from "../lib/failure";

export type AccessViewProps = {
  status: "loading" | "error" | "ready";
  entries?: ProjectAccessEntry[];
  /** Роль смотрящего: не владелец видит список без управления. */
  myRole: ProjectRole | null;
  failure?: Failure | null;
  /** Строка, над которой идёт запрос: "kind:id". */
  busyKey?: string | null;
  query: string;
  onQuery: (q: string) => void;
  candidates?: ProjectAccessCandidate[];
  candidatesLoading?: boolean;
  /** Поиск кандидатов не удался: это не то же самое, что «никого нет». */
  candidatesError?: boolean;
  onRetryCandidates?: () => void;
  adding?: boolean;
  /** Идентификатор смотрящего: его строка помечается. */
  selfId?: string | null;
  onRetry?: () => void;
  onAdd: (candidate: ProjectAccessCandidate, role: ProjectRole) => void;
  onChangeRole: (entry: ProjectAccessEntry, role: ProjectRole) => void;
  onRemove: (entry: ProjectAccessEntry) => void;
};

/** Роли, которые можно выдать здесь: владельца назначают отдельной передачей. */
const GRANTABLE: readonly ProjectRole[] = ["reader", "reviewer", "editor"];

const KIND_ICON = { user: UserRound, group: Users, org: Building2 } as const;

const rowKey = (e: { subject_kind: string; subject_id: string }) =>
  `${e.subject_kind}:${e.subject_id}`;

const CARD = {
  padding: 16,
  borderRadius: "var(--r-3)",
  border: "1px solid var(--border)",
  background: "var(--bg-1)",
  display: "flex",
  flexDirection: "column",
  gap: 12,
} as const;

/** Панель «Доступ» проекта: список людей и групп с ролями, добавление и смена роли. */
export const AccessView = ({
  status,
  entries = [],
  myRole,
  failure = null,
  busyKey = null,
  query,
  onQuery,
  candidates = [],
  candidatesLoading = false,
  candidatesError = false,
  onRetryCandidates,
  adding = false,
  selfId = null,
  onRetry,
  onAdd,
  onChangeRole,
  onRemove,
}: AccessViewProps) => {
  const { t } = useTranslation("projectAccess");
  const roleLabel = useProjectRoleLabel();
  const [role, setRole] = useState<ProjectRole>("reader");
  const canManage = myRole === "owner";
  const roleOptions = (list: readonly ProjectRole[]) =>
    list.map((r) => ({ value: r, label: roleLabel(r) }));

  return (
    <section style={CARD} data-testid="project-access" id="project-access">
      <div className="flex flex-col" style={{ gap: 3 }}>
        <h5 style={{ margin: 0, fontSize: 13.5, fontWeight: 600 }}>
          {t("panel.title")}
        </h5>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: 12 }}>
          {t("panel.lead")}
        </p>
      </div>

      {status === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          data-testid="access-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("panel.loading")}</span>
        </div>
      )}

      {status === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("panel.loadFailed")}
          action={
            onRetry && (
              <button type="button" className="btn xs" onClick={onRetry}>
                {t("panel.retry")}
              </button>
            )
          }
        />
      )}

      {status === "ready" && !canManage && myRole && (
        <Notice
          tone="info"
          text={t("panel.readOnly", { role: roleLabel(myRole) })}
        />
      )}

      {failure && (
        <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
      )}

      {status === "ready" && (
        <ul
          style={{ listStyle: "none", margin: 0, padding: 0 }}
          className="flex flex-col"
          data-testid="access-list"
        >
          {entries.map((entry) => {
            const Icon = KIND_ICON[entry.subject_kind];
            const key = rowKey(entry);
            const busy = busyKey === key;
            const editable =
              canManage && !entry.locked && entry.subject_kind !== "org";
            const detail =
              entry.subject_kind === "org"
                ? t("panel.orgRow")
                : entry.locked && entry.role === "owner"
                  ? t("panel.ownerRow")
                  : entry.detail;
            return (
              <li
                key={key}
                data-testid={`access-row-${key}`}
                className="flex items-center"
                style={{
                  gap: 12,
                  padding: "10px 0",
                  borderBottom: "1px dashed var(--border)",
                }}
              >
                <Icon
                  size={18}
                  aria-hidden="true"
                  style={{ color: "var(--fg-2)", flexShrink: 0 }}
                />
                <div
                  className="flex flex-col"
                  style={{ gap: 2, flex: 1, minWidth: 0 }}
                >
                  <span
                    className="flex items-center"
                    style={{
                      gap: 8,
                      fontSize: 13,
                      fontWeight: 500,
                      flexWrap: "wrap",
                    }}
                  >
                    <span style={{ overflowWrap: "anywhere" }}>
                      {entry.name}
                    </span>
                    <Badge variant="subtle">
                      {t(`panel.kind.${entry.subject_kind}`)}
                    </Badge>
                    {entry.subject_id === selfId && (
                      <Badge variant="info">{t("panel.you")}</Badge>
                    )}
                  </span>
                  {detail && (
                    <span
                      style={{
                        fontSize: 11.5,
                        color: "var(--fg-2)",
                        overflowWrap: "anywhere",
                      }}
                    >
                      {detail}
                    </span>
                  )}
                </div>
                {editable ? (
                  <>
                    <div
                      style={{ width: 150 }}
                      data-testid={`access-role-${key}`}
                    >
                      <Select
                        ariaLabel={t("panel.roleAria", { name: entry.name })}
                        value={entry.role}
                        isDisabled={busy}
                        options={roleOptions(GRANTABLE)}
                        onValueChange={(next) => {
                          onChangeRole(entry, next as ProjectRole);
                        }}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      disabled={busy}
                      aria-label={t("panel.removeAria", { name: entry.name })}
                      title={t("panel.remove")}
                      data-testid={`access-remove-${key}`}
                      onClick={() => {
                        onRemove(entry);
                      }}
                    >
                      {busy ? (
                        <Spinner size="sm" />
                      ) : (
                        <X size={14} aria-hidden="true" />
                      )}
                    </Button>
                  </>
                ) : (
                  <span
                    className="flex items-center"
                    style={{ gap: 6 }}
                    title={entry.locked ? t("panel.lockedHint") : undefined}
                    data-testid={`access-fixed-${key}`}
                  >
                    {entry.locked && (
                      <Lock
                        size={12}
                        aria-hidden="true"
                        style={{ color: "var(--fg-2)" }}
                      />
                    )}
                    <Badge
                      variant={entry.role === "owner" ? "accent" : "default"}
                    >
                      {roleLabel(entry.role)}
                    </Badge>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {status === "ready" && canManage && (
        <div
          className="flex flex-col"
          style={{ gap: 10 }}
          data-testid="access-add"
        >
          <strong style={{ fontSize: 12.5 }}>{t("panel.add.title")}</strong>
          <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <Input
                aria-label={t("panel.add.searchLabel")}
                placeholder={t("panel.add.search")}
                value={query}
                onChange={(e) => {
                  onQuery(e.target.value);
                }}
                data-testid="access-search"
              />
            </div>
            <div style={{ width: 150 }} data-testid="access-new-role">
              <Select
                ariaLabel={t("panel.add.role")}
                value={role}
                options={roleOptions(GRANTABLE)}
                onValueChange={(next) => {
                  setRole(next as ProjectRole);
                }}
              />
            </div>
          </div>
          <p style={{ margin: 0, fontSize: 11.5, color: "var(--fg-2)" }}>
            {t("panel.add.hint")}
          </p>
          {candidatesLoading && (
            <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
              <Spinner size="sm" />
              <span className="dim">{t("panel.add.loading")}</span>
            </div>
          )}
          {!candidatesLoading && candidatesError && (
            <div data-testid="access-search-error">
              <Notice
                tone="err"
                role="alert"
                text={t("panel.add.error")}
                action={
                  onRetryCandidates && (
                    <button
                      type="button"
                      className="btn xs"
                      onClick={onRetryCandidates}
                      data-testid="access-search-retry"
                    >
                      {t("panel.retry")}
                    </button>
                  )
                }
              />
            </div>
          )}
          {!candidatesLoading &&
            !candidatesError &&
            query.trim() !== "" &&
            candidates.length === 0 && (
              <p
                style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}
                data-testid="access-none"
              >
                {t("panel.add.none")}
              </p>
            )}
          {candidates.length > 0 && (
            <ul
              style={{ listStyle: "none", margin: 0, padding: 0 }}
              className="flex flex-col"
              data-testid="access-candidates"
            >
              {candidates.map((c) => {
                const Icon = KIND_ICON[c.subject_kind];
                const key = rowKey(c);
                return (
                  <li
                    key={key}
                    data-testid={`access-candidate-${key}`}
                    className="flex items-center"
                    style={{ gap: 12, padding: "8px 0" }}
                  >
                    <Icon
                      size={16}
                      aria-hidden="true"
                      style={{ color: "var(--fg-2)", flexShrink: 0 }}
                    />
                    <div
                      className="flex flex-col"
                      style={{ flex: 1, minWidth: 0 }}
                    >
                      <span style={{ fontSize: 13, fontWeight: 500 }}>
                        {c.name}
                      </span>
                      {c.detail && (
                        <span style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                          {c.detail}
                        </span>
                      )}
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      disabled={adding}
                      style={{ gap: 6 }}
                      data-testid={`access-add-${key}`}
                      onClick={() => {
                        onAdd(c, role);
                      }}
                    >
                      <Plus size={12} aria-hidden="true" />
                      {t("panel.add.button")}
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
};
