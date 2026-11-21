// Охрана несохранённых правок «Содержимого» (docs/design/pack-studio-ux.md, 12.7). Нужна, пока
// текст сохраняется кнопкой (временный редактор S8a): переход к другому документу или разделу
// иначе тихо потерял бы набранное. Редактор с автосохранением (S8b) её не использует.
// Состояние на уровне модуля: навигация и центр это разные слоты и общих props у них нет.

const dirty = new Set<string>();

/** Редактор `owner` сообщает, есть ли у него несохранённая правка. */
export const setContentDirty = (owner: string, value: boolean): void => {
  if (value) dirty.add(owner);
  else dirty.delete(owner);
};

export const hasContentUnsaved = (): boolean => dirty.size > 0;

/** `true`: можно уходить (правок нет или человек согласился их отбросить). */
export const confirmContentLeave = (message: string): boolean => {
  if (!hasContentUnsaved()) return true;
  if (!window.confirm(message)) return false;
  dirty.clear();
  return true;
};
