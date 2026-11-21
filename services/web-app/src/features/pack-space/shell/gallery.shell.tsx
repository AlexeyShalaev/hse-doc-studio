import type { GalleryEntry } from "@shared/lib/stateGallery";
import { SpaceGalleryFrame } from "../galleryKit";
import { SpaceScreen } from "./SpaceScreen";
import { defineSpaceSlots } from "./spaceSlots";

// Каркас на условных слотах: видно, где область кладёт свою часть. Настоящие слоты областей
// (S2 - S10) добавляют свои записи в собственные gallery.<область>.tsx.
const Demo = ({ children }: { children: string }) => (
  <div style={{ color: "var(--fg-2)", fontSize: "0.8125rem" }}>{children}</div>
);

const DEMO_SLOTS = defineSpaceSlots({
  changesButton: () => <button className="btn">Изменения</button>,
  nextStep: () => <button className="btn primary">Главная кнопка</button>,
  nav: { result: () => <Demo>Слот nav: что получает студент</Demo> },
  mainTop: { result: () => <Demo>Слот mainTop: для какого студента</Demo> },
  main: { result: () => <Demo>Слот main: части результата</Demo> },
  details: { result: () => <Demo>Слот details: почему так</Demo> },
  changes: () => <Demo>Слот changes: панель «Изменения»</Demo>,
});

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_shell_empty",
    title: "Каркас без областей: заглушка «Скоро»",
    note: "Название пространства, три вкладки, центр с заглушкой: так выглядит `?ux=2` до подключения срезов.",
    frame: "screen",
    width: 1280,
    render: () => (
      <SpaceGalleryFrame>
        <SpaceScreen slots={{}} phone={false} />
      </SpaceGalleryFrame>
    ),
  },
  {
    id: "sp_shell_desktop",
    title: "Десктоп, три колонки",
    note: "От 1100 px: слева «что», в центре результат, справа подробности.",
    frame: "screen",
    width: 1280,
    render: () => (
      <SpaceGalleryFrame>
        <SpaceScreen slots={DEMO_SLOTS} phone={false} />
      </SpaceGalleryFrame>
    ),
  },
  {
    id: "sp_shell_tablet",
    title: "Планшет, подробности выехали поверх",
    note: "768 - 1099 px: две колонки, подробности по выбору элемента, закрываются крестиком и Esc.",
    frame: "screen",
    width: 900,
    render: () => (
      <SpaceGalleryFrame search="sel=documents%3Ats">
        <SpaceScreen slots={DEMO_SLOTS} phone={false} />
      </SpaceGalleryFrame>
    ),
  },
  {
    id: "sp_shell_phone",
    title: "Телефон: нижние вкладки",
    note: "Слева ничего, подробности шторкой, внизу Результат, Содержимое, Проверка, Изменения.",
    frame: "plain",
    width: 390,
    render: () => (
      <SpaceGalleryFrame height="40rem" search="sel=documents%3Ats">
        <SpaceScreen slots={DEMO_SLOTS} phone />
      </SpaceGalleryFrame>
    ),
  },
  {
    id: "sp_shell_changes",
    title: "Панель «Изменения» открыта",
    frame: "screen",
    width: 1280,
    render: () => (
      <SpaceGalleryFrame search="changes=1">
        <SpaceScreen slots={DEMO_SLOTS} phone={false} />
      </SpaceGalleryFrame>
    ),
  },
];
