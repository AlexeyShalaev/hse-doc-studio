import {
  usePackOutcomeLint,
  type PackOutcomeLint,
} from "@entities/pack-studio";
import { countsOf, type LintCounts } from "../lib/lint";
import { useOutcomeModel } from "../model";

/**
 * Ответ линтера из кэша запроса. Сам расчёт идёт только в режиме «Проверка» (секунды и лимит
 * частоты), поэтому до первого открытия режима данных нет; запрос здесь выключен
 * (`enabled: false`) и лишь читает кэш под общим префиксом ключей версии: правка файла и запись
 * сценария его сбрасывают, значок не показывает устаревшие числа.
 */
export const useCachedLint = (): PackOutcomeLint | undefined => {
  const { workspaceId, ref, url } = useOutcomeModel();
  return usePackOutcomeLint(workspaceId, ref, { state: url.state.state }, false)
    .data;
};

/** Число находок по уровням из кэша; `null`, пока проверка не запускалась. */
export const useLintCounts = (): LintCounts | null => {
  const lint = useCachedLint();
  return lint ? countsOf(lint) : null;
};
