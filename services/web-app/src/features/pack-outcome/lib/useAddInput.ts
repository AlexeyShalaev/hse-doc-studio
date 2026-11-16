import { useEffect, useRef, useState } from "react";
import {
  usePackOutcomeExplain,
  type OutcomeElementRef,
  type PackOutcomeExplainRequest,
} from "@entities/pack-studio";
import { useOutcomeModel } from "../model";
import { useApplyInput } from "./applyInput";

/** Состояние элемента, которое «Добавить во вводных» ищет в «что если» сервера. */
export const wantedState = (
  element: OutcomeElementRef,
): "active" | "present" =>
  element.section === "documents" ? "active" : "present";

export type AddInput = {
  /** Ищу вводную: запрос `explain` идёт. */
  searching: boolean;
  /** Сервер не нашёл вводной, которая одна вернёт элемент. */
  none: boolean;
  /** Запрос не удался. */
  failed: boolean;
  run: () => void;
};

/**
 * «Добавить во вводных» бледного слота. Предложение целиком от сервера: запрос `explain` элемента
 * (те же вводные, что у расчёта) отдаёт `counterfactuals`, и применяется первая вводная, при
 * которой элемент становится `active` (документ) или `present` (остальные). Сервер уже отсортировал
 * вводные: сначала те, что блокируют элемент. Клиент ничего не придумывает: нет такой записи,
 * значит одной вводной элемент не вернуть и слот пишет об этом. Запрос идёт по нажатию, а не при
 * показе слота: бледных слотов много. Применение это одна вводная в адрес с записью в историю
 * (как «Что если» панели «Почему?»): «Назад» в браузере возвращает прежнюю комбинацию.
 */
export const useAddInput = (element: OutcomeElementRef): AddInput => {
  const { workspaceId, ref, request } = useOutcomeModel();
  const apply = useApplyInput();
  const body: PackOutcomeExplainRequest = {
    state: request.state,
    scenario: request.scenario,
    example: request.example,
    inputs: request.inputs,
    element,
  };
  const key = JSON.stringify(body);
  // Нажатие привязано к комбинации: сменились вводные, начинаем сначала.
  const [armed, setArmed] = useState<string | null>(null);
  const applied = useRef<string | null>(null);
  const query = usePackOutcomeExplain(workspaceId, ref, body, armed === key);
  const reply = query.data;
  // Прежний ответ того же элемента (при смене вводных) за ответ не считается.
  const ready = armed === key && !query.isPlaceholderData;
  const want = wantedState(element);
  const fix = ready
    ? reply?.counterfactuals.find((c) => c.result === want)
    : undefined;
  useEffect(() => {
    if (!fix || applied.current === key) return;
    applied.current = key;
    apply(fix.input, fix.value);
  }, [fix, key, apply]);
  return {
    searching: armed === key && !query.isError && reply === undefined,
    none: ready && reply !== undefined && fix === undefined,
    failed: armed === key && query.isError,
    run: () => {
      if (armed === key && query.isError) void query.refetch();
      applied.current = null;
      setArmed(key);
    },
  };
};
