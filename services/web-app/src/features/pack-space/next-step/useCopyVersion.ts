import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  SPACE_QUERY,
  packErrorText,
  packStudioKeys,
  useCreatePackVersion,
  type PackVersionCreated,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { useSpace } from "../context/SpaceContext";
import type { SpaceNavPatch } from "../context/nav";
import { useSpaceNav } from "../context/useSpaceNav";
import { takenSuggestion } from "./submitErrors";

/** Параметры «Содержимого», которые переживают переход к копии (сегмент и запись манифеста). */
const KEEP = ["seg", "at"] as const;

/**
 * Куда человек смотрел, переписанное на копию: тот же документ, раздел и файл, только каталог
 * версии новый (копия повторяет структуру). Только для вкладки «Содержимое»; «Результат» и
 * «Проверка» сохраняют выбранный элемент сами.
 */
export const carryPlace = (
  search: string,
  from: string | null,
  to: string,
): SpaceNavPatch => {
  const params = new URLSearchParams(search);
  const file = params.get(SPACE_QUERY.file);
  const patch: SpaceNavPatch = {
    doc: params.get(SPACE_QUERY.doc),
    part: params.get(SPACE_QUERY.part),
    file:
      file !== null && from !== null && file.startsWith(`${from}/`)
        ? `${to}${file.slice(from.length)}`
        : file,
    sel: params.get(SPACE_QUERY.sel),
    extra: Object.fromEntries(KEEP.map((name) => [name, params.get(name)])),
  };
  return patch;
};

/**
 * «Править копию» выпущенной версии (pack-studio-ux.md, 5.3, 9.3 S4): черновик со следующим
 * номером создаётся без окна выбора класса, человек остаётся на этом же экране. Класс
 * «небольшая правка» (следующий patch); если номер уже занят в основной ветке, берётся
 * свободный, который подсказал сервер (прежнее `takeSuggested`). `minor` и `major` выбираются
 * позже, в «Изменить номер».
 *
 * Это единственный способ сделать копию на экране: главная кнопка полосы, «Подробности»,
 * «Содержимое» (текст, подписи, части версии, все файлы) зовут его же (S13). С `toastOnError`
 * отказ показывается всплывающим сообщением (там, где у кнопки нет места под строку ошибки).
 */
export const useCopyVersion = ({
  toastOnError = false,
}: { toastOnError?: boolean } = {}) => {
  const { workspace, versionRef, version, location } = useSpace();
  const nav = useSpaceNav();
  const client = useQueryClient();
  const create = useCreatePackVersion(workspace.id);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const running = useRef(false);
  const { mutateAsync } = create;

  const make = (next?: string): Promise<PackVersionCreated> =>
    mutateAsync({
      pack: versionRef.pack,
      template: versionRef.template,
      body: next
        ? { base: versionRef.version, version: next }
        : { base: versionRef.version, update_class: "patch" },
    });

  const run = async (): Promise<boolean> => {
    // Второе нажатие, пока копия создаётся, ничего не делает: иначе выйдут две копии.
    if (running.current) return false;
    running.current = true;
    setPending(true);
    setError(null);
    try {
      let created: PackVersionCreated;
      try {
        created = await make();
      } catch (first) {
        const free = takenSuggestion(first);
        if (free === null) throw first;
        created = await make(free);
      }
      // Дерево должно знать новую версию, иначе экран не найдёт её по адресу.
      await client.refetchQueries({
        queryKey: packStudioKeys.tree(workspace.id),
      });
      nav.go({
        ref: {
          pack: created.version.pack,
          template: created.version.template,
          version: created.version.version,
        },
        ...carryPlace(
          location.search,
          version?.path ?? null,
          created.version.path,
        ),
      });
      return true;
    } catch (failure) {
      setError(failure);
      if (toastOnError) toast.error(packErrorText(failure));
      return false;
    } finally {
      running.current = false;
      setPending(false);
    }
  };
  return { run, pending, error };
};
