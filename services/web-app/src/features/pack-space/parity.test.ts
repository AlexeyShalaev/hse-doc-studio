import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Карта паритета (pack-studio-ux.md, 7.4): Студия шаблонов открывает только этот интерфейс (S14),
// поэтому каждая функция прежнего вида должна быть в карте с отметкой «сделано» и закрыта тестом.
// Тест ломается, если строку карты добавили без теста, сняли отметку «сделано», переименовали или
// удалили тест, на который она ссылается, или убрали его файл из колонки «Тест» карты.

const SRC = join(import.meta.dirname, "../..");
const DOC = readFileSync(
  join(SRC, "../../../docs/design/pack-studio-ux.md"),
  "utf8",
);

/** [функция прежнего вида (первая колонка карты), файл теста от `src/`, имя теста]. */
const ROWS: readonly (readonly [string, string, string])[] = [
  [
    "Создать пространство (git, папка), официальные паки",
    "features/pack-workspaces/ui/workspaces.test.tsx",
    "подключение репозитория: три клика и одно поле",
  ],
  [
    "Создать пространство (git, папка), официальные паки",
    "features/pack-workspaces/ui/workspaces.test.tsx",
    "папка: одно поле и «Выбрать папку…», отказ сервера показан словами",
  ],
  [
    "Создать пространство (git, папка), официальные паки",
    "features/pack-workspaces/ui/official.test.tsx",
    "токен из окна: проверка под packs_fork, доступ выбран, кнопка включена",
  ],
  [
    "Повторить клонирование, обновить базу, удалить",
    "features/pack-workspaces/ui/workspaces.test.tsx",
    "повтор и удаление: у неудавшегося «Проверить доступ», повтор и удаление в меню",
  ],
  [
    "Повторить клонирование, обновить базу, удалить",
    "features/pack-space/nav/SpaceBar.test.tsx",
    "«Обновить» просит обновить пространство",
  ],
  [
    "Повторить клонирование, обновить базу, удалить",
    "features/pack-space/nav/SpaceBar.test.tsx",
    "удаление спрашивает, объясняет и уходит в список",
  ],
  [
    "Выбор пака, шаблона, версии",
    "features/pack-space/nav/ContextBar.test.tsx",
    "список версий: состояние у каждой и пометки, выбор меняет адрес",
  ],
  [
    "Выбор пака, шаблона, версии",
    "features/pack-space/nav/ContextBar.test.tsx",
    "смена шаблона сохраняет условия студента и вкладку",
  ],
  [
    "Выбор пака, шаблона, версии",
    "features/pack-space/nav/WhereSheet.test.tsx",
    "пак переключается сразу, шторка остаётся; версия закрывает её",
  ],
  [
    "Создать пак, шаблон",
    "features/pack-space/nav/ContextBar.test.tsx",
    "в меню пака и шаблона есть «Создать пак» и «Создать шаблон»",
  ],
  [
    "Создать пак, шаблон",
    "features/pack-space/content/parts/parts.test.tsx",
    "без файла: подсказка выбрать файл и дерево; создание пака и шаблона по месту",
  ],
  [
    "Подключить к каталогу локальной Студии",
    "features/pack-space/nav/SpaceBar.test.tsx",
    "папка в локальной Студии: «Подключить к каталогу Студии» открывает окно каталога",
  ],
  [
    "Условия студента, сброс",
    "features/pack-space/situation/SituationBar.test.tsx",
    "условие меняется за два клика, значение уходит в адрес",
  ],
  [
    "Условия студента, сброс",
    "features/pack-space/situation/SituationBar.test.tsx",
    "меню «Ещё»: сбросить, запомнить, сравнить",
  ],
  [
    "Сценарии (выбор, прогон, сохранить)",
    "features/pack-space/situation/SituationBar.test.tsx",
    "готовый случай ставит свои условия; без него условия сбрасываются",
  ],
  [
    "Сценарии (выбор, прогон, сохранить)",
    "features/pack-space/situation/SaveCaseDialog.test.tsx",
    "записывает условия с экрана и выбирает новый случай",
  ],
  [
    "Сценарии (выбор, прогон, сохранить)",
    "features/pack-space/check/cases.test.tsx",
    "«Проверить заново» запрашивает таблицу ещё раз",
  ],
  [
    "Документы, данные, участники, точки сдачи, маршрут, анкеты",
    "features/pack-space/result/result.test.tsx",
    "строка документа: название, файл и языки, кнопка PDF",
  ],
  [
    "Документы, данные, участники, точки сдачи, маршрут, анкеты",
    "features/pack-space/result/result.test.tsx",
    "данные проекта: поля по группам, бейджи, анкеты",
  ],
  [
    "Документы, данные, участники, точки сдачи, маршрут, анкеты",
    "features/pack-space/result/result.test.tsx",
    "участники: роль, имя и организация",
  ],
  [
    "Документы, данные, участники, точки сдачи, маршрут, анкеты",
    "features/pack-space/result/result.test.tsx",
    "сроки и сдача: срок словами и что сдаётся",
  ],
  [
    "Документы, данные, участники, точки сдачи, маршрут, анкеты",
    "features/pack-space/result/result.test.tsx",
    "подписи: порядок словами и число подписей",
  ],
  [
    "Фильтры списка документов, поиск",
    "features/pack-space/result/result.test.tsx",
    "поиск и фильтр документов появляются, только когда документов больше десяти",
  ],
  [
    "«Почему?», «Что изменится, если…»",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "«Почему так» предложениями, без идентификаторов и путей",
  ],
  [
    "«Почему?», «Что изменится, если…»",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "«Что изменится, если…» ставит условие на экран, «Вернуть» его снимает",
  ],
  [
    "Править правило, убрать условие, удалить слот",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "мини-форма подписана фразой, чипы пишут в черновик, видна разница",
  ],
  [
    "Править правило, убрать условие, удалить слот",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "«Убрать условие» снимает условие из файла версии, «Отменить» в ленте его возвращает",
  ],
  [
    "Править правило, убрать условие, удалить слот",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "условие подписи: список с понятными подписями",
  ],
  [
    "Отменить, повторить, лента правок",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "Ctrl+Z и Ctrl+Shift+Z отменяют и повторяют правку",
  ],
  [
    "Отменить, повторить, лента правок",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "«Ещё»: история правок с кнопками «Отменить» и «Повторить»",
  ],
  [
    "Открыть правило, исходник",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "идентификаторы и файлы только в «Технических подробностях»",
  ],
  [
    "Создать новую версию",
    "features/pack-space/next-step/NextStepButton.test.tsx",
    "выпущенная версия без правок: «Править копию» создаёт версию без окна и остаётся на экране",
  ],
  [
    "Создать новую версию",
    "features/pack-space/details/DetailsPanel.test.tsx",
    "вместо «Изменить условия» кнопка «Править копию», она создаёт копию и остаётся на экране",
  ],
  [
    "Редактор файла, формы версии, документа, полей, анкет, сроков",
    "features/pack-space/content/text/TextEditor.test.tsx",
    "правка записывается сама через 1,5 секунды, рядом «записано»",
  ],
  [
    "Редактор файла, формы версии, документа, полей, анкет, сроков",
    "features/pack-space/content/parts/parts.test.tsx",
    "указатель записи доходит до формы",
  ],
  [
    "Редактор файла, формы версии, документа, полей, анкет, сроков",
    "features/pack-space/content/parts/parity.test.ts",
    "каждый раздел формы версии открывается из какого-то раздела навигации",
  ],
  [
    "Места подписей",
    "features/pack-space/content/signatures/SignaturesView.test.tsx",
    "перетаскивание пишет место документа со сборкой и If-Match",
  ],
  [
    "Места подписей",
    "features/pack-space/content/signatures/SignaturesOverview.test.tsx",
    "какие подписи есть, где стоят, в каких документах: простыми словами",
  ],
  [
    "Проблемы",
    "features/pack-space/preview/ContentPreview.test.tsx",
    "замечания к файлу: число и порядок (ошибка раньше), чужого файла нет",
  ],
  [
    "Проблемы",
    "features/pack-space/check/check.test.tsx",
    "итог одной фразой, находки по уровням, как исправить",
  ],
  [
    "Проблемы",
    "features/pack-space/check/check.test.tsx",
    "«Открыть место в файле» ведёт в «Содержимое» с файлом версии",
  ],
  [
    "Предпросмотр, сборка, журнал, варианты",
    "features/pack-space/preview/PreviewPanel.test.tsx",
    "собирает сам при открытии: по условиям из адреса и примеру по умолчанию, без единого выбора",
  ],
  [
    "Предпросмотр, сборка, журнал, варианты",
    "features/pack-space/preview/PreviewPanel.test.tsx",
    "сборка не удалась: причина словами, «Собрать ещё раз» и журнал; слов про Jinja и LaTeX нет",
  ],
  [
    "Предпросмотр, сборка, журнал, варианты",
    "features/pack-space/preview/PreviewPanel.test.tsx",
    "варианты документа выбираются тут же; вариант без PDF предупреждён",
  ],
  [
    "Предпросмотр, сборка, журнал, варианты",
    "features/pack-space/preview/ResultPreview.test.tsx",
    "по кнопке «PDF» в строке (sel и preview=1) панель открывает предпросмотр выбранного документа",
  ],
  [
    "Матрица, Атлас, Сравнить, покрытие, проверка Jinja",
    "features/pack-space/check/check.test.tsx",
    "три части и сравнение, открытая отмечена, у «Замечаний» число",
  ],
  [
    "Матрица, Атлас, Сравнить, покрытие, проверка Jinja",
    "features/pack-space/check/check.test.tsx",
    "какие правила проверены готовыми случаями: процент и «Добавить готовые случаи»",
  ],
  [
    "Матрица, Атлас, Сравнить, покрытие, проверка Jinja",
    "features/pack-space/check/check.test.tsx",
    "находки человеческими словами: текст сервера, правило и файл только в технических подробностях (V1)",
  ],
  [
    "Матрица, Атлас, Сравнить, покрытие, проверка Jinja",
    "features/pack-space/check/check.test.tsx",
    "`compare=1`: экран сравнения со стороны слева и справа, подписи без внутренних слов",
  ],
  [
    "Статус git, ветка, правки, отставание",
    "features/pack-space/changes/ChangesDrawer.test.tsx",
    "готово: число на кнопке, что изменено человеческими словами, проверки чистые",
  ],
  [
    "Статус git, ветка, правки, отставание",
    "features/pack-space/changes/ChangesDrawer.test.tsx",
    "основная ветка ушла вперёд: плашка и «Забрать новое»",
  ],
  [
    "Diff, коммит, ветка, подтянуть, сбросить, доступ, форк, CI",
    "features/pack-space/changes/ChangesDrawer.test.tsx",
    "меню «Ещё» панели: сохранить точку, ветка, доступ; построчное сравнение с основной веткой",
  ],
  [
    "Diff, коммит, ветка, подтянуть, сбросить, доступ, форк, CI",
    "features/pack-space/changes/ChangesDrawer.test.tsx",
    "«Сбросить все мои изменения»: окно с теми же словами, без «свежей main без ветки»",
  ],
  [
    "Diff, коммит, ветка, подтянуть, сбросить, доступ, форк, CI",
    "features/pack-space/changes/ChangesDrawer.test.tsx",
    "запрос открыт: проверки на хостинге, ссылка, можно продолжать править",
  ],
  [
    "Diff, коммит, ветка, подтянуть, сбросить, доступ, форк, CI",
    "features/pack-space/next-step/submit.test.tsx",
    "нет права писать в репозиторий: форк, указать свою копию и отправить в неё",
  ],
  [
    "Предложить изменения, официальные паки, лицензия",
    "features/pack-space/next-step/submit.test.tsx",
    "всё готово: выпуск, затем отправка одной кнопкой; запрос открылся",
  ],
  [
    "Предложить изменения, официальные паки, лицензия",
    "features/pack-space/next-step/submit.test.tsx",
    "официальные паки: без согласия с лицензией отправить нельзя",
  ],
  [
    "Предложить изменения, официальные паки, лицензия",
    "features/pack-space/next-step/submit.test.tsx",
    "не прошла проверка перед отправкой: находки по месту, переход к файлу",
  ],
  [
    "Выпустить, номер, заметки",
    "features/pack-space/next-step/submit.test.tsx",
    "без галочки выпуска версия не выпускается",
  ],
  [
    "Выпустить, номер, заметки",
    "features/pack-space/next-step/submit.test.tsx",
    "«изменить номер»: классы словами, номер меняется, экран идёт за версией",
  ],
  [
    "Выпустить, номер, заметки",
    "features/pack-space/next-step/submit.test.tsx",
    "«Подсказать по изменениям» остаётся: заполняет поля, автозапись пишет",
  ],
  [
    "Перенести правки в новую версию",
    "features/pack-space/changes/ChangesDrawer.test.tsx",
    "выпущенную версию правили мимо Студии: «Перенести правки» в копию и переход к ней",
  ],
  [
    "Дерево файлов",
    "features/pack-space/content/parts/parts.test.tsx",
    "клик по файлу открывает его заменой записи",
  ],
  [
    "Нижние вкладки, шторки",
    "features/pack-space/phone/phone.test.tsx",
    "четыре вкладки, текущая отмечена, число изменённых файлов на «Изменениях»",
  ],
  [
    "Нижние вкладки, шторки",
    "features/pack-space/phone/phone.test.tsx",
    "выбор элемента открывает шторку с ручкой, крестиком и затемнением",
  ],
  [
    "Админка Студии (включить, право, доступы, официальные паки)",
    "features/pack-studio-admin/ui/PackStudioAdminPage.test.tsx",
    "включение раздела и права людям и группам, снятие права",
  ],
  [
    "Админка Студии (включить, право, доступы, официальные паки)",
    "features/pack-studio-admin/ui/PackStudioAdminPage.test.tsx",
    "служебные доступы: список без секрета, добавление с токеном, удаление с подтверждением",
  ],
  [
    "Админка Студии (включить, право, доступы, официальные паки)",
    "features/pack-studio-admin/ui/PackStudioAdminPage.test.tsx",
    "официальные паки: только адрес репозитория, без бота, выключателя и лимита",
  ],
  [
    "Матрица: окно сценария из строки или клетки",
    "features/pack-space/check/cases.test.tsx",
    "«Открыть случай» из строки",
  ],
  [
    "Матрица: окно сценария из строки или клетки",
    "features/pack-space/check/cases.test.tsx",
    "«Открыть случай» из клетки",
  ],
  [
    "Матрица: редактор утверждений сценария",
    "features/pack-space/check/cases.test.tsx",
    "редактор ожиданий: убрать, добавить из предложенного, сохранить",
  ],
  [
    "Матрица: принять текущий результат как ожидаемый",
    "features/pack-space/check/cases.test.tsx",
    "«Принять текущий результат как ожидаемый» пишет снимок",
  ],
  [
    "Матрица: удалить сценарий",
    "features/pack-space/check/cases.test.tsx",
    "удаление просит подтверждение",
  ],
  [
    "Матрица: вид «Как студент» у сценария",
    "features/pack-space/check/cases.test.tsx",
    "«Так увидит студент» открывает вид студента",
  ],
  [
    "Матрица: стрелки, Home и End по таблице",
    "features/pack-space/check/cases.test.tsx",
    "в Tab-порядке одна клетка; стрелки, Home, End и Ctrl",
  ],
  [
    "Матрица: выпущенная версия, сценарии для чтения",
    "features/pack-space/check/cases.test.tsx",
    "выпущенная версия: окно только для чтения",
  ],
  [
    "Матрица: относительно ожидаемого или основной версии",
    "features/pack-space/check/check.test.tsx",
    "переключатель «Относительно» пишет `against` в адрес",
  ],
  [
    "Матрица: прогнать заново",
    "features/pack-space/check/cases.test.tsx",
    "«Проверить заново» запрашивает таблицу ещё раз",
  ],
  [
    "Матрица: статусы клеток и буквы групп",
    "features/pack-space/check/check.test.tsx",
    "таблица: готовые случаи в строках, части результата в столбцах",
  ],
  [
    "Матрица: показать результат и сравнить",
    "features/pack-space/check/check.test.tsx",
    "клетка показывает, что в ней, и ведёт к результату или сравнению",
  ],
  [
    "Атлас: карточки условий и «Зафиксировать»",
    "features/pack-space/check/check.test.tsx",
    "значение условия фиксируется в адресе и снимается",
  ],
  [
    "Атлас: слишком много вариантов, что зафиксировать",
    "features/pack-space/check/check.test.tsx",
    "слишком много вариантов: объяснение и выбор, что зафиксировать",
  ],
  [
    "Атлас: переключатель «Строки / По результатам»",
    "features/pack-space/check/cases.test.tsx",
    "переключатель «По сочетаниям» и «По результатам»",
  ],
  [
    "Атлас: сортировка",
    "features/pack-space/check/cases.test.tsx",
    "порядок «Сначала частые»",
  ],
  [
    "Атлас: фильтры по условиям",
    "features/pack-space/check/cases.test.tsx",
    "фильтр по условию сужает список сочетаний",
  ],
  [
    "Атлас: фильтр по варианту результата",
    "features/pack-space/check/cases.test.tsx",
    "«Показать эти сочетания» возвращает к строкам только этого варианта",
  ],
  [
    "Атлас: пометка «сейчас на экране»",
    "features/pack-space/check/cases.test.tsx",
    "«Сейчас на экране»: вариант результата для условий экрана",
  ],
  [
    "Атлас: поиск",
    "features/pack-space/check/cases.test.tsx",
    "поиск среди вариантов сужает список",
  ],
  [
    "Атлас: показать результат варианта",
    "features/pack-space/check/check.test.tsx",
    "все варианты за кнопкой; вариант открывается в «Результате»",
  ],
  [
    "Сравнить: подписи изменений",
    "features/pack-space/check/check.test.tsx",
    "подписи изменений словами: роли по-русски",
  ],
];

/**
 * Строки без компонентного теста: интерфейс их не меняет. MCP и командная строка не затронуты,
 * справку и сайт держат `make docs-lint` и сборка сайта; слова интерфейса держит тест словаря.
 */
const OUTSIDE_UI = new Set(["MCP, CLI, справка, сайт документации"]);

type MapRow = { was: string; done: string; tests: string };

/** Строки карты 7.4: функция, отметка «сделано» и колонка «Тест». */
const MAP: readonly MapRow[] = (() => {
  const start = DOC.indexOf("### 7.4.");
  const end = DOC.indexOf("\n## ", start);
  return DOC.slice(start, end)
    .split("\n")
    .filter((line) => line.startsWith("| ") && !line.startsWith("| Функция"))
    .map((line) => line.split("|").map((cell) => cell.trim()))
    .filter((cells) => !/^-+$/.test(cells[1] ?? ""))
    .map((cells) => ({
      was: cells[1] ?? "",
      done: cells[5] ?? "",
      tests: cells[6] ?? "",
    }));
})();

const sources = new Map<string, string>();
const source = (file: string): string => {
  let text = sources.get(file);
  if (text === undefined) {
    const path = join(SRC, file);
    text = existsSync(path) ? readFileSync(path, "utf8") : "";
    sources.set(file, text);
  }
  return text;
};

const fileName = (file: string): string => file.split("/").pop() ?? file;

describe("карта паритета 7.4: прежний вид Студии убран, функции на месте (S14)", () => {
  it("в карте все функции и у каждой отметка «сделано»", () => {
    expect(MAP.length).toBeGreaterThanOrEqual(48);
    for (const row of MAP) {
      expect(row.done, row.was).toBe("сделано");
    }
  });

  it("каждая строка карты закрыта тестом, у каждого теста строка в карте", () => {
    const known = new Set(ROWS.map(([was]) => was));
    for (const row of MAP) {
      if (OUTSIDE_UI.has(row.was)) continue;
      expect(known.has(row.was), row.was).toBe(true);
    }
    const listed = new Set(MAP.map((row) => row.was));
    for (const was of known) expect(listed.has(was), was).toBe(true);
  });

  it("тест есть в своём файле, а файл назван в колонке «Тест» карты", () => {
    for (const [was, file, test] of ROWS) {
      expect(source(file), `${was}: ${file}`).toContain(test);
      const row = MAP.find((item) => item.was === was);
      expect(row?.tests ?? "", `${was}: ${file}`).toContain(fileName(file));
    }
  });
});
