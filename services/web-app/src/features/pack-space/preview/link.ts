import type { SpaceNavPatch } from "../context/nav";

// Предпросмотр PDF «Результата» (pack-studio-ux.md, 5.4 пункт 4): параметр `preview=1` просит
// правую панель открыть предпросмотр выбранного документа. Кнопка «PDF» в строке документа ставит
// его вместе с `sel`. Только данные, без React: файл безопасно тянуть из любого слота.

export const PREVIEW_PARAM = "preview";

/** Открыть (`true`) или скрыть предпросмотр выбранного документа. */
export const previewPatch = (open: boolean): SpaceNavPatch => ({
  extra: { [PREVIEW_PARAM]: open ? "1" : null },
});

/** Предпросмотр просили открыть: по адресу вкладки. */
export const isPreviewOpen = (search: string): boolean =>
  new URLSearchParams(search).get(PREVIEW_PARAM) === "1";
