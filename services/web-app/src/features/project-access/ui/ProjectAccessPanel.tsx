import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { useProjectRoleLabel } from "@entities/project";
import {
  useBootstrap,
  type ProjectAccessCandidate,
  type ProjectAccessEntry,
  type ProjectRole,
} from "@entities/session";
import {
  useAccessCandidates,
  useProjectAccess,
  useRemoveAccess,
  useSetAccess,
} from "../api/projectAccessQueries";
import type { Failure } from "../lib/failure";
import { AccessView } from "./AccessView";

/** Панель «Доступ» в настройках проекта: список, добавление человека или группы, смена роли. */
export const ProjectAccessPanel = ({
  projectId,
  myRole,
}: {
  projectId: string;
  myRole: ProjectRole | null;
}) => {
  const { t } = useTranslation("projectAccess");
  const roleLabel = useProjectRoleLabel();
  const selfId = useBootstrap().data?.user?.id ?? null;
  const list = useProjectAccess(projectId);
  const [query, setQuery] = useState("");
  const canManage = myRole === "owner";
  const candidates = useAccessCandidates(
    projectId,
    query.trim(),
    canManage && query.trim() !== "",
  );
  const set = useSetAccess(projectId);
  const remove = useRemoveAccess(projectId);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  // Отказ по роли показывает общий тост с названием роли; остальные коды панель пишет сама.
  const fail = (error: unknown) => {
    const code = failureCode(error);
    setFailure(code === "forbidden_role" ? null : { code });
  };

  const apply = (
    entry: { subject_kind: "user" | "group"; subject_id: string },
    name: string,
    role: ProjectRole,
    toastKey: "added" | "changed",
  ) => {
    setFailure(null);
    setBusyKey(`${entry.subject_kind}:${entry.subject_id}`);
    set.mutate(
      {
        subject_kind: entry.subject_kind,
        subject_id: entry.subject_id,
        role,
      },
      {
        onSuccess: () => {
          toast.success(
            t(`panel.toast.${toastKey}`, { name, role: roleLabel(role) }),
          );
          if (toastKey === "added") setQuery("");
        },
        onError: fail,
        onSettled: () => {
          setBusyKey(null);
        },
      },
    );
  };

  return (
    <AccessView
      status={list.data ? "ready" : list.isError ? "error" : "loading"}
      entries={list.data ?? []}
      myRole={myRole}
      failure={failure}
      busyKey={busyKey}
      query={query}
      onQuery={setQuery}
      candidates={candidates.data ?? []}
      candidatesLoading={candidates.isFetching && query.trim() !== ""}
      candidatesError={candidates.isError && query.trim() !== ""}
      onRetryCandidates={() => {
        void candidates.refetch();
      }}
      adding={set.isPending}
      selfId={selfId}
      onRetry={() => {
        void list.refetch();
      }}
      onAdd={(c: ProjectAccessCandidate, role) => {
        apply(c, c.name, role, "added");
      }}
      onChangeRole={(e: ProjectAccessEntry, role) => {
        if (e.subject_kind === "org") return;
        apply(
          { subject_kind: e.subject_kind, subject_id: e.subject_id },
          e.name,
          role,
          "changed",
        );
      }}
      onRemove={(e) => {
        if (e.subject_kind === "org") return;
        setFailure(null);
        setBusyKey(`${e.subject_kind}:${e.subject_id}`);
        remove.mutate(
          { kind: e.subject_kind, id: e.subject_id },
          {
            onSuccess: () => {
              toast.success(t("panel.toast.removed", { name: e.name }));
            },
            onError: fail,
            onSettled: () => {
              setBusyKey(null);
            },
          },
        );
      }}
    />
  );
};
