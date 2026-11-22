import type { GalleryEntry } from "@shared/lib/stateGallery";
import { SpaceGalleryFrame } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import {
  COMPARE_SEARCH,
  seedCases,
  seedCompare,
  seedLint,
  seedMap,
  seedVersion,
} from "./seeds";
import { slots } from "./slots";

// Вкладка «Проверка» в галерее (`/dev/server-screens`): данные из seeds.ts.

const screen = (search: string, phone = false, height?: string) => (
  <SpaceGalleryFrame
    tab="check"
    search={search}
    height={height ?? (phone ? "44rem" : "40rem")}
  >
    <SpaceScreen slots={slots} phone={phone} />
  </SpaceGalleryFrame>
);

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_check_issues",
    title: "Проверка: замечания",
    note: "Итог одной фразой, находки по уровням с подсказкой «Как исправить», какие правила проверены готовыми случаями.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedLint(client, "normal");
    },
    render: () => screen(""),
  },
  {
    id: "sp_check_issues_plain",
    title: "Проверка: замечания человеческими словами",
    note: "Названия пака вместо идентификаторов («Согласование темы», «Научный руководитель»), «Как исправить» вместо подсказок сервера; сырой текст сервера в «Технические подробности».",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedLint(client, "named");
    },
    render: () => screen(""),
  },
  {
    id: "sp_check_issues_clean",
    title: "Проверка: замечаний нет",
    note: "Пустое состояние объясняет, что всё хорошо, и ведёт к следующему шагу.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedLint(client, "clean");
    },
    render: () => screen(""),
  },
  {
    id: "sp_check_issues_skipped",
    title: "Проверка: часть проверок пропущена",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedLint(client, "skipped");
    },
    render: () => screen(""),
  },
  {
    id: "sp_check_issues_loading",
    title: "Проверка: считаю",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedLint(client, "loading");
    },
    render: () => screen(""),
  },
  {
    id: "sp_check_issues_rate",
    title: "Проверка: слишком много проверок",
    note: "Отказ человеческими словами и одно действие «Повторить».",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedLint(client, "rate_limited");
    },
    render: () => screen(""),
  },
  {
    id: "sp_check_cases",
    title: "Типовые случаи",
    note: "Таблица готовых случаев и частей результата; клетка показывает статус значком и словом.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedCases(client, "ready");
    },
    render: () => screen("part=cases"),
  },
  {
    id: "sp_check_case_dialog",
    title: "Типовые случаи: окно случая",
    note: "«Открыть случай» из строки: итог проверки, «Принять текущий результат как ожидаемый», «Что должно получаться» словами (убрать, добавить), «Так увидит студент», «Удалить случай».",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedCases(client, "ready");
    },
    render: () => screen("part=cases&open=company-supervisor"),
  },
  {
    id: "sp_check_case_failed",
    title: "Типовые случаи: случай не сошёлся",
    note: "Что не сошлось словами («Ожидали: ...»), чем результат отличается от ожидаемого, сырое сравнение сервера в технических подробностях.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedCases(client, "ready");
    },
    render: () => screen("part=cases&open=university-supervisor"),
  },
  {
    id: "sp_check_case_student",
    title: "Типовые случаи: «Так увидит студент»",
    note: "Документы, что заполнить и кто подписывает при условиях самого случая; слова по словарю нового интерфейса.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedCases(client, "ready");
    },
    render: () => screen("part=cases&student=company-supervisor"),
  },
  {
    id: "sp_check_case_released",
    title: "Типовые случаи: выпущенная версия",
    note: "Окно случая только для чтения: «Править копию» вместо правки, принятия и удаления.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedVersion("2026.1.2");
      seedCases(client, "ready");
      seedVersion();
    },
    render: () => (
      <SpaceGalleryFrame
        tab="check"
        search="part=cases&open=company-supervisor"
        version="2026.1.2"
        height="40rem"
      >
        <SpaceScreen slots={slots} phone={false} />
      </SpaceGalleryFrame>
    ),
  },
  {
    id: "sp_check_case_phone",
    title: "Типовые случаи: окно случая на телефоне",
    note: "Окно становится шторкой снизу, все действия достижимы.",
    frame: "plain",
    width: 390,
    seed: (client) => {
      seedCases(client, "ready");
    },
    render: () => screen("part=cases&open=university-supervisor", true),
  },
  {
    id: "sp_check_cases_empty",
    title: "Типовые случаи: пока нет",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedCases(client, "empty");
    },
    render: () => screen("part=cases"),
  },
  {
    id: "sp_check_map",
    title: "Что на что влияет",
    note: "Карточки условий с «Меняет: ...» и кнопкой фиксации, число вариантов результата.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedMap(client, "ready");
    },
    render: () => screen("part=map"),
  },
  {
    id: "sp_check_map_outcomes",
    title: "Что на что влияет: по результатам",
    note: "«Сейчас на экране» вверху, переключатель «По сочетаниям / По результатам», порядок и фильтры по условиям; у варианта результата сколько сочетаний условий к нему ведёт.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedMap(client, "ready");
    },
    render: () => screen("part=map&all=1&group=outcomes", false, "58rem"),
  },
  {
    id: "sp_check_map_rows",
    title: "Что на что влияет: по сочетаниям",
    note: "Список сочетаний условий с пометкой «Сейчас на экране» и фильтрами.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedMap(client, "ready");
    },
    render: () => screen("part=map&all=1", false, "58rem"),
  },
  {
    id: "sp_check_map_too_many",
    title: "Что на что влияет: слишком много вариантов",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedMap(client, "too_many");
    },
    render: () => screen("part=map"),
  },
  {
    id: "sp_check_compare",
    title: "Сравнить с другой ситуацией",
    note: "Не вкладка, а экран `?compare=1`: внутри прежнее сравнение двух сторон.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedCompare(client);
    },
    render: () => screen(COMPARE_SEARCH),
  },
  {
    id: "sp_check_issues_phone",
    title: "Проверка на телефоне",
    note: "Левой колонки нет: части переключаются полосой над заголовком.",
    frame: "plain",
    width: 390,
    seed: (client) => {
      seedLint(client, "normal");
    },
    render: () => screen("", true),
  },
  {
    id: "sp_check_cases_phone",
    title: "Типовые случаи на телефоне",
    note: "Таблица прокручивается внутри своей рамки, страница не уезжает вбок.",
    frame: "plain",
    width: 390,
    seed: (client) => {
      seedCases(client, "ready");
    },
    render: () => screen("part=cases", true),
  },
];
