import { useMemo } from "react";
import { useSpace } from "../context/SpaceContext";
import { NO_CHANGES, type ChangesStatus } from "./types";

/**
 * Состояние изменений пространства. Каркас (S0) отдаёт заглушку «ничего не изменено» с тем, что
 * известно без запросов (вид пространства, подключение, замок версии). Срез S3 заменяет тело:
 * читает git, проверки, линтер и сведения о версии, собирает `deriveChangesStatus(raw)`.
 */
export const useChangesStatus = (): ChangesStatus => {
  const { workspace, released } = useSpace();
  return useMemo(
    () => ({
      ...NO_CHANGES,
      connection:
        workspace.state === "ready"
          ? "ready"
          : workspace.state === "cloning"
            ? "cloning"
            : "failed",
      workspaceKind: workspace.kind,
      released,
    }),
    [workspace.state, workspace.kind, released],
  );
};
