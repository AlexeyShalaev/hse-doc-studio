import type { QueryClient } from "@tanstack/react-query";
import { packOutcomeKeys } from "../api/outcomeQueries";
import type { PackVersionModel } from "../api/schemas";
import type { PackVersionRef } from "../api/packStudioApi";
import { packStudioKeys } from "../api/queries";

/**
 * Ответ правки модели версии ложится в кэш: модель, файлы, подсказки и всё, что считалось по
 * манифесту (git, места подписей, результат). Один путь для вкладки «Форма» и правки по месту
 * на экране «Результат»: обе стороны видят запись сразу.
 */
export const cacheModelResult = (
  client: QueryClient,
  workspaceId: string,
  ref: PackVersionRef,
  next: PackVersionModel,
): void => {
  client.setQueryData(packStudioKeys.model(workspaceId, ref), next);
  for (const path of next.changed) {
    void client.invalidateQueries({
      queryKey: packStudioKeys.file(workspaceId, path),
    });
  }
  const created = next.changed.some(
    (path) => !path.endsWith("version.yaml") && !path.endsWith("doc.yaml"),
  );
  if (created) {
    void client.invalidateQueries({
      queryKey: packStudioKeys.tree(workspaceId),
    });
  }
  void client.invalidateQueries({
    queryKey: packStudioKeys.hints(
      workspaceId,
      next.manifest.path.replace(/\/version\.yaml$/, ""),
    ),
  });
  // Результат версии зависит от манифестов: расчёт, «Почему?» и вводные считаются заново.
  void client.invalidateQueries({
    queryKey: packOutcomeKeys.version(workspaceId, ref),
  });
};

/**
 * Файл манифеста записан целиком (откат правки по месту возвращает прежний текст): кэш файла,
 * подсказки, результат и модель версии обновляются; модель перечитывается и ждётся, чтобы
 * следующая правка опиралась на новый ETag.
 */
export const refreshAfterFileWrite = async (
  client: QueryClient,
  workspaceId: string,
  ref: PackVersionRef,
  path: string,
): Promise<void> => {
  void client.invalidateQueries({
    queryKey: packStudioKeys.file(workspaceId, path),
  });
  void client.invalidateQueries({
    queryKey: packStudioKeys.hints(
      workspaceId,
      path.replace(/\/(version|files\/[^/]+\/doc)\.yaml$/, ""),
    ),
  });
  void client.invalidateQueries({
    queryKey: packOutcomeKeys.version(workspaceId, ref),
  });
  await client.refetchQueries({
    queryKey: packStudioKeys.model(workspaceId, ref),
  });
};
