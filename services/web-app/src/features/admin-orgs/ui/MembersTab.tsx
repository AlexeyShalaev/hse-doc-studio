import { useState } from "react";
import { failureCode } from "@shared/api";
import type { OrgRoleName } from "@entities/session";
import {
  useAddMember,
  useMembers,
  useRemoveMember,
  useSetRole,
} from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
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
  const members = useMembers(slug);
  const add = useAddMember(slug);
  const setRole = useSetRole(slug);
  const remove = useRemoveMember(slug);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [addFailure, setAddFailure] = useState<Failure | null>(null);

  const status = members.isError
    ? "error"
    : members.isPending
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
      members={members.data ?? []}
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
      onAdd={(email: string, role: OrgRoleName) =>
        add.mutateAsync({ email, role }).then(
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
