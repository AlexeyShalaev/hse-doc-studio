import { useEffect, useState } from "react";
import type { Extension } from "@codemirror/state";
import { ySyncAnnotation } from "y-codemirror.next";
import { useRouteEditGuard } from "@entities/signing-route";
import { createEditGate } from "@shared/ui";

/**
 * Мягкое предупреждение в редакторе исходников (signing-route.md, 12.7): первая правка файла
 * документа на подписании (или общего файла) ждёт ответа до применения, «Отмена» оставляет текст
 * как был. Фильтр создаётся с редактором один раз, вопрос привязывается к нему здесь. Правки
 * соавторов (совместная сессия) и подмена текста хостом не спрашивают.
 */
export const useRouteEditGate = (
  projectId: string,
  relativePath: string,
): Extension => {
  const guard = useRouteEditGuard(projectId);
  const [gate] = useState(() => createEditGate({ exempt: [ySyncAnnotation] }));
  useEffect(() => {
    const target = { paths: [relativePath] };
    gate.bind({
      shouldAsk: () => guard.pending(target).length > 0,
      ask: () => guard.confirm(target),
    });
    return () => {
      gate.bind(null);
    };
  }, [gate, guard, relativePath]);
  return gate.extension;
};
