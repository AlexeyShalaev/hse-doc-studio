import { useMemo } from "react";
import {
  describeCloudDoc,
  describeLocalDoc,
  useCloudBuilds,
  useLocalBuilds,
  type DocBuildView,
} from "@entities/project-build";
import { useBootstrap } from "@entities/session";

export type DocBuilds = {
  mode: "server" | "local" | null;
  /** По документу: что показать. Пусто, пока данных нет или проект не связан с облаком. */
  byDoc: ReadonlyMap<string, DocBuildView>;
  /** Документы, у которых в облаке есть сборка, а у этой Студии нет (или там свежее). */
  fetchable: readonly string[];
  /** Нет связи с облаком: причина для подсказки. */
  error: string | null;
};

const EMPTY: ReadonlyMap<string, DocBuildView> = new Map();

/**
 * Статус сборок документов проекта: в облаке по таблице сборок и выгруженным PDF, в локальной Студии по локальным
 * записям и ответу сервера. Один хук и один вид (`DocBuildView`) для обоих режимов.
 */
export const useDocBuilds = (projectId: string): DocBuilds => {
  const mode = useBootstrap().data?.mode ?? null;
  const cloud = useCloudBuilds(projectId, mode === "server");
  const local = useLocalBuilds(projectId, mode === "local");
  return useMemo<DocBuilds>(() => {
    if (mode === "server" && cloud.data !== undefined) {
      return {
        mode,
        byDoc: new Map(
          cloud.data.documents.map((d) => [d.doc_id, describeCloudDoc(d)]),
        ),
        fetchable: [],
        error: null,
      };
    }
    if (mode === "local" && local.data?.connected === true) {
      const data = local.data;
      return {
        mode,
        byDoc: new Map(
          data.documents.map((d) => [d.doc_id, describeLocalDoc(d)]),
        ),
        fetchable: data.documents
          .filter((d) => d.can_fetch)
          .map((d) => d.doc_id),
        error: data.cloud_error,
      };
    }
    return { mode, byDoc: EMPTY, fetchable: [], error: null };
  }, [mode, cloud.data, local.data]);
};
