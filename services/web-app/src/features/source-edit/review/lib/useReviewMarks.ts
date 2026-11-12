import { useEffect, useMemo, useState, type RefObject } from "react";
import {
  resolveAnchor,
  type ResolvedAnchor,
  type TextReviewThread,
} from "@entities/review";
import type { CodeEditorController } from "@shared/ui";
import { setReviewMarks } from "./reviewMarks";

const RESOLVE_DEBOUNCE_MS = 400;

/**
 * Привязывает треды к живому тексту редактора: пересчёт при смене тредов и (с паузой) при правках,
 * результат кладётся в подсветку и возвращается панели («сдвинут», «изменён», «оторван»).
 */
export const useReviewMarks = (
  controller: RefObject<CodeEditorController | null>,
  threads: TextReviewThread[],
  activeId: string | null,
  docRevision: number,
  showResolved: boolean,
): Map<string, ResolvedAnchor> => {
  const [resolved, setResolved] = useState<Map<string, ResolvedAnchor>>(
    () => new Map(),
  );

  useEffect(() => {
    const run = (): void => {
      const view = controller.current?.view();
      if (!view) return;
      const text = view.state.doc.toString();
      const next = new Map<string, ResolvedAnchor>();
      for (const thread of threads)
        next.set(thread.id, resolveAnchor(text, thread.anchor));
      setResolved(next);
    };
    const timer = setTimeout(run, docRevision === 0 ? 0 : RESOLVE_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [controller, threads, docRevision]);

  const marks = useMemo(
    () =>
      threads.flatMap((thread) => {
        const found = resolved.get(thread.id);
        if (!found || found.state === "lost") return [];
        if (
          thread.status === "resolved" &&
          !showResolved &&
          thread.id !== activeId
        )
          return [];
        return [
          {
            id: thread.id,
            from: found.from,
            to: found.to,
            resolved: thread.status === "resolved",
            active: thread.id === activeId,
          },
        ];
      }),
    [threads, resolved, activeId, showResolved],
  );

  useEffect(() => {
    controller.current?.view()?.dispatch({ effects: setReviewMarks.of(marks) });
  }, [controller, marks]);

  return resolved;
};
