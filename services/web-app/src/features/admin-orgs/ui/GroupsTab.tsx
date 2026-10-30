import { useState } from "react";
import { failureCode } from "@shared/api";
import {
  useCreateGroup,
  useDeleteGroup,
  useGroups,
  useMembers,
  useUpdateGroup,
} from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
import { GroupsView } from "./GroupsView";

const asFailure = (error: unknown): Failure => ({ code: failureCode(error) });

export const GroupsTab = ({ slug }: { slug: string }) => {
  const groups = useGroups(slug);
  const members = useMembers(slug);
  const create = useCreateGroup(slug);
  const update = useUpdateGroup(slug);
  const remove = useDeleteGroup(slug);
  const [formFailure, setFormFailure] = useState<Failure | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  const status =
    groups.isError || members.isError
      ? "error"
      : groups.isPending || members.isPending
        ? "loading"
        : "ready";

  return (
    <GroupsView
      status={status}
      groups={groups.data ?? []}
      members={members.data ?? []}
      formFailure={formFailure}
      failure={failure}
      saving={create.isPending || update.isPending}
      deleting={remove.isPending}
      onRetry={() => {
        void groups.refetch();
        void members.refetch();
      }}
      onReset={() => {
        setFormFailure(null);
        setFailure(null);
      }}
      onCreate={(draft) =>
        create
          .mutateAsync({ name: draft.name, member_ids: draft.memberIds })
          .then(
            () => true,
            (error: unknown) => {
              setFormFailure(asFailure(error));
              return false;
            },
          )
      }
      onUpdate={(group, draft) =>
        update
          .mutateAsync({
            id: group.id,
            body: { name: draft.name, member_ids: draft.memberIds },
          })
          .then(
            () => true,
            (error: unknown) => {
              setFormFailure(asFailure(error));
              return false;
            },
          )
      }
      onDelete={(group) =>
        remove.mutateAsync(group.id).then(
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
