const DRAG_MIME = "application/x-hse-path";

/** Перетаскивают файлы с компьютера, а не строку дерева (у неё свой тип application/x-hse-path). */
export const isExternalDrag = (dataTransfer: DataTransfer): boolean => {
  const types = Array.from(dataTransfer.types);
  return types.includes("Files") && !types.includes(DRAG_MIME);
};
