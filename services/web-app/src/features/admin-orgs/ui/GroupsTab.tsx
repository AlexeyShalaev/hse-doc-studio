import { useMemo, useState } from "react";
import { failureCode } from "@shared/api";
import { useListQueryState, useServerList } from "@shared/lib";
import { adminPickers } from "@entities/session";
import { adminOrgsApi } from "../api/adminOrgsApi";
import {
  adminOrgsKeys,
  useCreateGroup,
  useDeleteGroup,
  useRenameGroup,
} from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
import { GROUPS_LIST } from "../lib/listState";
import { GroupsView } from "./GroupsView";

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

export const GroupsTab = ({ slug }: { slug: string }) => {
  const state = useListQueryState(GROUPS_LIST);
  const groups = useServerList({
    state,
    queryKey: adminOrgsKeys.groups(slug),
    fetchPage: (params, signal) => adminOrgsApi.groups(slug, params, signal),
  });
  // Участников группы ищут среди участников организации на сервере.
  // Для существующей группы пикер не предлагает тех, кто в ней уже есть.
  const memberSource = useMemo(
    () => (groupId: string | null) =>
      adminPickers.orgMembers(slug, groupId ?? undefined),
    [slug],
  );
  const create = useCreateGroup(slug);
  const rename = useRenameGroup(slug);
  const remove = useDeleteGroup(slug);
  const [formFailure, setFormFailure] = useState<Failure | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  const status =
    groups.isError && groups.items.length === 0
      ? "error"
      : groups.isLoading
        ? "loading"
        : "ready";

  const settle = (promise: Promise<unknown>, onFail: (f: Failure) => void) =>
    promise.then(
      () => true,
      (error: unknown) => {
        onFail(asFailure(error));
        return false;
      },
    );

  return (
    <GroupsView
      status={status}
      groups={groups.items}
      slug={slug}
      memberSource={memberSource}
      total={groups.isLoading ? null : groups.total}
      pagination={groups.pagination}
      fetching={groups.isFetching}
      formFailure={formFailure}
      failure={failure}
      saving={create.isPending || rename.isPending}
      deleting={remove.isPending}
      onRetry={() => {
        void groups.refetch();
      }}
      onReset={() => {
        setFormFailure(null);
        setFailure(null);
      }}
      onCreate={(draft) =>
        settle(
          create.mutateAsync({ name: draft.name, member_ids: draft.memberIds }),
          setFormFailure,
        )
      }
      onRename={(group, name) =>
        settle(rename.mutateAsync({ id: group.id, name }), setFormFailure)
      }
      onDelete={(group) => settle(remove.mutateAsync(group.id), setFailure)}
    />
  );
};
