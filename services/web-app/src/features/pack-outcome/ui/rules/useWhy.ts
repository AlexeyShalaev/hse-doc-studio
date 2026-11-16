import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  isElementGone,
  packOutcomeKeys,
  usePackOutcomeExplain,
  type OutcomeElementRef,
  type PackOutcomeExplainRequest,
} from "@entities/pack-studio";
import { useOutcomeModel } from "../../model";

/**
 * «Почему?» выбранного элемента: запрос `explain` с теми же вводными, что у расчёта. Если сервер
 * ответил 404 `outcome_element_not_found` (версия или вводные поменялись, и элемент исчез),
 * результат обновляется молча, а выбор снимается: показывать нечего.
 */
export const useWhy = (element: OutcomeElementRef) => {
  const { workspaceId, ref, request, url } = useOutcomeModel();
  const client = useQueryClient();
  const body: PackOutcomeExplainRequest = {
    state: request.state,
    scenario: request.scenario,
    example: request.example,
    inputs: request.inputs,
    element,
  };
  const query = usePackOutcomeExplain(workspaceId, ref, body);
  const gone = isElementGone(query.error);
  const { update } = url;
  useEffect(() => {
    if (!gone) return;
    void client.invalidateQueries({
      queryKey: packOutcomeKeys.version(workspaceId, ref),
    });
    update({ selected: null });
  }, [gone, client, workspaceId, ref, update]);
  return { query, gone };
};
