import type { GalleryEntry } from "@shared/lib/stateGallery";
import { SpaceProvider } from "../context/SpaceContext";
import { GALLERY_TREE, GALLERY_WORKSPACE } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { defineSpaceSlots } from "../shell/spaceSlots";
import { EDITED, TREE, WS, seedNav } from "./fixtures";
import { NoPlace } from "./NoPlace";
import { WhereBody } from "./WhereSheet";
import { slots as navSlots } from "./slots";
import { useWhere } from "./useWhere";
import "./space-nav.css";

// Записи галереи области nav: полосы пространства, версия с моими изменениями «в другом месте»,
// телефон и шторка «Куда перейти». Данные лежат в кэше запросов, сервера нет.

// Кнопки «Изменения» и главная принадлежат S3 и S4: здесь условные, чтобы полоса выглядела целой.
const SLOTS = defineSpaceSlots({
  ...navSlots,
  changesButton: () => <button className="btn">Изменения · 3</button>,
  nextStep: () => <button className="btn primary">Главная кнопка</button>,
});

const Frame = ({
  version,
  height = "26rem",
  children,
}: {
  version: string;
  height?: string;
  children: React.ReactNode;
}) => (
  <div
    className="ui-console"
    style={{ display: "flex", flexDirection: "column", height }}
  >
    <SpaceProvider
      workspace={GALLERY_WORKSPACE}
      tree={TREE}
      versionRef={{ pack: "hse-cs-sse", template: "coursework", version }}
      tab="result"
      location={{
        pathname: "/pack-studio",
        search: "",
        navigate: () => undefined,
      }}
    >
      {children}
    </SpaceProvider>
  </div>
);

const SheetDemo = () => {
  const where = useWhere();
  return (
    <div
      style={{
        position: "relative",
        flex: 1,
        background: "color-mix(in oklch, var(--bg-0) 55%, black)",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: "auto 0 0 0",
          maxHeight: "92%",
          overflow: "auto",
          background: "var(--bg-1)",
          borderRadius: "1rem 1rem 0 0",
          boxShadow: "var(--shadow-pop)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            padding: "1rem 1rem 0.5rem",
            fontWeight: 600,
          }}
        >
          Куда перейти
        </div>
        <WhereBody
          where={where}
          onCreate={() => undefined}
          onDone={() => undefined}
        />
      </div>
    </div>
  );
};

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_nav_draft",
    title: "Полосы: черновик с моими изменениями",
    note: "Пространство и «Ещё», пак › шаблон › версия со словом «черновик», три вкладки.",
    frame: "screen",
    width: 1280,
    seed: seedNav(EDITED),
    render: () => (
      <Frame version="2026.1.3">
        <SpaceScreen slots={SLOTS} phone={false} />
      </Frame>
    ),
  },
  {
    id: "sp_nav_released",
    title: "Полосы: выпущенная версия, правки в другой версии",
    note: "У версии замок и слово «выпущена». В списке версий сверху «Мои правки: к черновику».",
    frame: "screen",
    width: 1280,
    seed: seedNav(EDITED),
    render: () => (
      <Frame version="2026.1.2">
        <SpaceScreen slots={SLOTS} phone={false} />
      </Frame>
    ),
  },
  {
    id: "sp_nav_tablet",
    title: "Полосы на планшете",
    note: "768 - 1099 px: те же крошки и вкладки, строка переносится.",
    frame: "screen",
    width: 900,
    seed: seedNav(EDITED),
    render: () => (
      <Frame version="2026.1.3">
        <SpaceScreen slots={SLOTS} phone={false} />
      </Frame>
    ),
  },
  {
    id: "sp_nav_phone",
    title: "Телефон: одна кнопка «Куда перейти»",
    note: "Три крошки стали одной кнопкой с состоянием версии; вкладок здесь нет, они внизу.",
    frame: "plain",
    width: 390,
    seed: seedNav(EDITED),
    render: () => (
      <Frame version="2026.1.3" height="40rem">
        <SpaceScreen slots={SLOTS} phone />
      </Frame>
    ),
  },
  {
    id: "sp_nav_phone_where",
    title: "Телефон: шторка «Куда перейти»",
    note: "Сверху «Мои правки» прямо к черновику, ниже пак, шаблон и версия.",
    frame: "plain",
    width: 390,
    seed: seedNav(EDITED),
    render: () => (
      <Frame version="2026.1.2" height="44rem">
        <SheetDemo />
      </Frame>
    ),
  },
  {
    id: "sp_nav_empty",
    title: "В пространстве нет паков",
    note: "Причина и один следующий шаг: «Создать пак».",
    frame: "plain",
    width: 720,
    render: () => (
      <NoPlace workspaceId={WS} tree={{ ...GALLERY_TREE, packs: [] }} />
    ),
  },
];
