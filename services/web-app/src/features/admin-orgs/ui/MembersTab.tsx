import { useMemo, useState } from "react";
import { failureCode } from "@shared/api";
import { useListQueryState, useServerList } from "@shared/lib";
import { adminPickers } from "@entities/session";
import { adminOrgsApi } from "../api/adminOrgsApi";
import {
  adminOrgsKeys,
  useAddMember,
  useMemberFacets,
  useOrg,
  useRemoveMember,
  useSetRole,
} from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
import { MEMBERS_LIST } from "../lib/listState";
import type { Viewer } from "../lib/permissions";
import { MembersView } from "./MembersView";

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

export const MembersTab = ({
  slug,
  viewer,
  selfId,
}: {
  slug: string;
  viewer: Viewer;
  selfId: string | null;
}) => {
  const state = useListQueryState(MEMBERS_LIST);
  const members = useServerList({
    state,
    queryKey: adminOrgsKeys.members(slug),
    fetchPage: (params, signal) => adminOrgsApi.members(slug, params, signal),
  });
  const facets = useMemberFacets(slug, state.q).data;
  const ownerCount = useOrg(slug).data?.owner_count ?? null;
  const add = useAddMember(slug);
  const setRole = useSetRole(slug);
  const remove = useRemoveMember(slug);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [addFailure, setAddFailure] = useState<Failure | null>(null);
  // Людей установки ищет только её админ: админу организации остаётся почта.
  const peopleSource = useMemo(
    () =>
      viewer.instanceAdmin
        ? adminPickers.users({ status: "active", notInOrg: slug })
        : null,
    [viewer.instanceAdmin, slug],
  );

  const status =
    members.isError && members.items.length === 0
      ? "error"
      : members.isLoading
        ? "loading"
        : "ready";
  const busyUserId = setRole.isPending
    ? setRole.variables.userId
    : remove.isPending
      ? remove.variables
      : null;

  return (
    <MembersView
      status={status}
      members={members.items}
      total={members.isLoading ? null : members.total}
      pagination={members.pagination}
      fetching={members.isFetching}
      roleCounts={facets?.role ?? null}
      ownerCount={ownerCount}
      peopleSource={peopleSource}
      viewer={viewer}
      selfId={selfId}
      failure={failure}
      addFailure={addFailure}
      adding={add.isPending}
      busyUserId={busyUserId}
      removing={remove.isPending}
      onRetry={() => {
        void members.refetch();
      }}
      onReset={() => {
        setFailure(null);
        setAddFailure(null);
      }}
      onAdd={(input) =>
        add.mutateAsync(input).then(
          () => true,
          (error: unknown) => {
            setAddFailure(asFailure(error));
            return false;
          },
        )
      }
      onSetRole={(member, role) => {
        setFailure(null);
        setAddFailure(null);
        setRole.mutate(
          { userId: member.user_id, role },
          {
            onError: (error) => {
              setFailure(asFailure(error));
            },
          },
        );
      }}
      onRemove={(member) =>
        remove.mutateAsync(member.user_id).then(
          () => true,
          (error: unknown) => {
            setFailure(asFailure(error));
            return false;
          },
        )
      }
    />
  );
};
