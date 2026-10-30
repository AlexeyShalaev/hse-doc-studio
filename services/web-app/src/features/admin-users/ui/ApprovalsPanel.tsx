import { useState } from "react";
import { Check, CheckCheck, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import {
  toast,
  useListQueryState,
  useServerList,
  type ListStateOptions,
} from "@shared/lib";
import {
  Button,
  EmptyState,
  ErrorState,
  FilterBar,
  NoResults,
  Pagination,
  offsetPagerShown,
  PersonCell,
  Section,
  SortSelect,
  Spinner,
  TableSkeleton,
} from "@shared/ui";
import type { AdminUser } from "@entities/session";
import { adminUsersApi } from "../api/adminUsersApi";
import {
  adminUsersKeys,
  useApprovalCount,
  useDecideApproval,
} from "../api/adminUsersQueries";
import type { Failure } from "../lib/failure";
import { FailureNotice, When } from "./parts";

type ApprovalSort = "created_at" | "name" | "email";

// Старые заявки первыми: они ждут дольше всех. Порядок задаёт сервер.
const LIST: ListStateOptions<never, ApprovalSort> = {
  sort: { fields: ["created_at", "name", "email"], default: "created_at" },
};

/** Вкладка «Одобрения»: очередь заявок, решение в строке и одобрение пачкой. */
export const ApprovalsPanel = () => {
  const { t } = useTranslation("adminUsers");
  const state = useListQueryState(LIST);
  const list = useServerList({
    state,
    queryKey: adminUsersKeys.approvalsList(),
    fetchPage: adminUsersApi.approvalsPage,
  });
  // Сколько всего ждёт решения: тот же запрос, что у числа на вкладке.
  const waiting = useApprovalCount().data ?? list.total;
  const decide = useDecideApproval();
  const [failure, setFailure] = useState<Failure | null>(null);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  // Строка, по которой идёт запрос; при пачке все отмеченные.
  const [working, setWorking] = useState<ReadonlySet<string>>(new Set());
  // Ход пачки: заявки решаются по одной, кнопка показывает, сколько готово.
  const [progress, setProgress] = useState<number | null>(null);

  // Выбор живёт в пределах одной страницы: на другой странице, поиске или
  // порядке отмеченные строки не видны, и пачка не должна их задевать.
  const view = JSON.stringify(state.params);
  const [selectedIn, setSelectedIn] = useState(view);
  if (selectedIn !== view) {
    setSelectedIn(view);
    setSelected(new Set());
  }

  const items = list.items;
  const total = list.total;
  const chosen = items.filter((u) => selected.has(u.id));
  const allChosen = items.length > 0 && chosen.length === items.length;
  const busy = working.size > 0;

  const decideOne = async (
    user: AdminUser,
    approve: boolean,
    batch = false,
  ) => {
    await decide.mutateAsync({ id: user.id, approve, batch });
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(user.id);
      return next;
    });
  };

  const go = (user: AdminUser, approve: boolean) => {
    setFailure(null);
    setWorking(new Set([user.id]));
    decideOne(user, approve)
      .then(
        () => {
          toast.success(
            t(approve ? "approvals.approved" : "approvals.rejected", {
              name: user.name,
            }),
          );
        },
        (error: unknown) => {
          setFailure({ code: failureCode(error) });
        },
      )
      .finally(() => {
        setWorking(new Set());
      });
  };

  const approveMany = async (people: readonly AdminUser[]) => {
    setFailure(null);
    setWorking(new Set(people.map((u) => u.id)));
    setProgress(0);
    let done = 0;
    try {
      // По одному: сервер решает каждую заявку отдельно, отказ одной не трогает остальные.
      for (const user of people) {
        await decideOne(user, true, true);
        done += 1;
        setProgress(done);
      }
    } catch (error: unknown) {
      setFailure({ code: failureCode(error) });
    } finally {
      setWorking(new Set());
      setProgress(null);
      // Списки, счётчики и журнал перечитываются один раз за пачку, а не на каждую заявку.
      if (done > 0) decide.refresh();
      if (done > 0) toast.success(t("approvals.approvedMany", { count: done }));
    }
  };

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (list.isLoading) {
    return (
      <div data-testid="approvals-panel">
        <TableSkeleton rows={3} columns={3} withAvatar />
      </div>
    );
  }
  if (list.isError) {
    return (
      <div data-testid="approvals-panel">
        <ErrorState
          framed
          title={t("approvals.loadFailed")}
          retrying={list.isFetching}
          onRetry={() => {
            void list.refetch();
          }}
        />
      </div>
    );
  }
  if (items.length === 0 && !state.isFiltered) {
    return (
      <div data-testid="approvals-panel">
        <EmptyState
          framed
          testId="approvals-empty"
          icon={<CheckCheck size={18} />}
          title={t("approvals.empty.title")}
          description={t("approvals.empty.body")}
        />
      </div>
    );
  }

  const bulk = chosen.length > 0 ? chosen : items;
  // На странице не все заявки: кнопка честно говорит, что одобрит только видимые.
  const partial = total > items.length;

  return (
    <div className="ppl-stack" data-testid="approvals-panel">
      <FilterBar
        search={state.q}
        onSearchChange={state.setQ}
        searchLabel={t("users.search")}
        searchPlaceholder={t("users.search")}
        busy={list.isFetching}
        onReset={state.reset}
        extra={
          <SortSelect
            sort={state.sort}
            onChange={state.setSort}
            label={t("sort.label")}
            testId="approvals-sort"
            options={[
              { field: "created_at", desc: false, label: t("sort.waiting") },
              { field: "created_at", desc: true, label: t("sort.newest") },
              { field: "name", desc: false, label: t("sort.name") },
              { field: "email", desc: false, label: t("sort.email") },
            ]}
          />
        }
      />
      {failure && <FailureNotice failure={failure} />}
      <Section
        title={t("approvals.title", { count: waiting })}
        description={t("approvals.lead")}
        flush
        actions={
          <Button
            size="sm"
            type="button"
            disabled={busy || items.length === 0}
            data-testid="approve-bulk"
            onClick={() => {
              void approveMany(bulk);
            }}
          >
            {busy && working.size > 1 ? (
              <Spinner size="sm" />
            ) : (
              <CheckCheck size={14} aria-hidden="true" />
            )}
            {progress !== null && working.size > 1
              ? t("approvals.approving", {
                  done: progress,
                  total: working.size,
                })
              : chosen.length > 0
                ? t("approvals.approveSelected", { count: chosen.length })
                : partial
                  ? t("approvals.approveShown", { count: items.length })
                  : t("approvals.approveAll", { count: items.length })}
          </Button>
        }
      >
        {items.length === 0 && (
          <NoResults compact query={state.searchOnly} onReset={state.reset} />
        )}
        {items.length > 0 && (
          <div className="ppl-queue-head">
            <label>
              <input
                type="checkbox"
                className="ppl-check"
                checked={allChosen}
                ref={(node) => {
                  if (node)
                    node.indeterminate = chosen.length > 0 && !allChosen;
                }}
                disabled={busy}
                aria-label={t("approvals.selectAll")}
                onChange={() => {
                  setSelected(
                    allChosen ? new Set() : new Set(items.map((u) => u.id)),
                  );
                }}
              />
              {chosen.length > 0
                ? t("approvals.selected", { count: chosen.length })
                : t("approvals.selectAll")}
            </label>
          </div>
        )}
        <ul
          className="ppl-queue"
          aria-label={t("approvals.caption")}
          aria-busy={list.isFetching}
          style={{ opacity: list.isFetching && !busy ? 0.6 : 1 }}
        >
          {items.map((u) => {
            const rowBusy = working.has(u.id);
            return (
              <li
                key={u.id}
                className="ppl-queue-row"
                data-selected={selected.has(u.id) ? "true" : undefined}
                data-testid={`approval-${u.id}`}
              >
                <input
                  type="checkbox"
                  className="ppl-check"
                  checked={selected.has(u.id)}
                  disabled={busy}
                  aria-label={t("approvals.select", { name: u.name })}
                  onChange={() => {
                    toggle(u.id);
                  }}
                />
                <span className="ppl-queue-person">
                  <PersonCell name={u.name} email={u.email} id={u.id} />
                </span>
                <span className="ppl-queue-when">
                  {t("approvals.since")} <When iso={u.created_at} />
                </span>
                <span className="ppl-queue-buttons">
                  <Button
                    size="sm"
                    variant="ghost"
                    type="button"
                    disabled={busy}
                    data-testid={`reject-${u.id}`}
                    aria-label={t("approvals.rejectAria", { name: u.name })}
                    onClick={() => {
                      go(u, false);
                    }}
                  >
                    <X size={14} aria-hidden="true" />
                    {t("approvals.reject")}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    type="button"
                    disabled={busy}
                    data-testid={`approve-${u.id}`}
                    aria-label={t("approvals.approveAria", { name: u.name })}
                    onClick={() => {
                      go(u, true);
                    }}
                  >
                    {rowBusy && working.size === 1 ? (
                      <Spinner size="sm" />
                    ) : (
                      <Check size={14} aria-hidden="true" />
                    )}
                    {t("approvals.approve")}
                  </Button>
                </span>
              </li>
            );
          })}
        </ul>
        {offsetPagerShown(list.pagination) && (
          <div className="adm-section-foot">
            <Pagination {...list.pagination} />
          </div>
        )}
      </Section>
    </div>
  );
};
