import { expect, test, type Page } from "@playwright/test";
import { LANGS, USERS, shot, type Lang } from "./helpers";
import {
  MIN_TOUCH,
  SIZES,
  closeToasts,
  expectNoHorizontalScroll,
  expectTouchTarget,
  loginOnPhone,
} from "./phoneHelpers";
import { mockBuiltPdf, mockPeopleAndStudios } from "./phoneMocks";

/**
 * Телефон на стенде server-lite: вход, список проектов, шторки вместо окон, нет горизонтальной прокрутки,
 * зоны касания не меньше 40 px. Два размера (360x740 и 390x844) и два языка интерфейса (его задаёт локаль браузера).
 * Скриншоты: screenshots/<язык>/mobile-<ширина>-*.png.
 */
for (const lang of LANGS) {
  for (const size of SIZES) {
    test.describe(`Телефон ${String(size.width)} [${lang}]`, () => {
      test.use({
        locale: lang === "ru" ? "ru-RU" : "en-US",
        viewport: size,
        hasTouch: true,
        isMobile: true,
      });
      const name = (suffix: string): string =>
        `mobile-${String(size.width)}-${suffix}`;

      test("гостевые экраны помещаются в окно", async ({ page }) => {
        for (const path of ["/", "/login", "/register", "/forgot"]) {
          await page.goto(path);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
        }
        await page.goto("/");
        await shot(page, lang as Lang, name("01-landing"));
        await page.goto("/login");
        await shot(page, lang as Lang, name("02-login"));
      });

      test("вход, список проектов, открыть проект", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await page.waitForLoadState("networkidle");
        await expectNoHorizontalScroll(page);
        for (const own of USERS.anna.projects) {
          await expect(
            page.locator(`[data-project-card][aria-label="${own}"]`),
          ).toBeVisible();
        }
        await shot(page, lang as Lang, name("03-projects"));

        await page.locator("[data-project-card]").first().click();
        await expect(page).toHaveURL(/\/projects\/[^/]+\/documents/);
        await shot(page, lang as Lang, name("04-project"));
      });

      test("зоны касания основных кнопок не меньше 40 px", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.waitForLoadState("networkidle");
        await expectTouchTarget(
          page,
          page.getByTestId("account-menu-trigger"),
          "меню аккаунта",
        );
        await expectTouchTarget(
          page,
          page.getByTestId("welcome-filters-trigger"),
          "фильтры",
        );
        await expectTouchTarget(
          page,
          page.locator("[data-tour=home-new-project]"),
          "новый проект",
        );
        await expectTouchTarget(
          page,
          page.getByRole("button", { name: /Импорт|Import/ }).first(),
          "импорт",
        );
        const small = await page.evaluate((min) => {
          const out: string[] = [];
          for (const el of document.querySelectorAll(
            "button, a[href], input, select, textarea, [role=button]",
          )) {
            const rect = el.getBoundingClientRect();
            if (
              rect.width === 0 ||
              rect.height === 0 ||
              el.closest("[aria-hidden=true]")
            )
              continue;
            if (
              el instanceof HTMLInputElement &&
              ["checkbox", "radio"].includes(el.type)
            )
              continue;
            if (Math.min(rect.width, rect.height) < min - 0.5) {
              out.push(
                `${el.tagName.toLowerCase()} ${String(Math.round(rect.width))}x${String(Math.round(rect.height))} ${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30)}`,
              );
            }
          }
          return out;
        }, MIN_TOUCH);
        expect(small).toEqual([]);
      });

      test("фильтры открываются шторкой и применяются сразу", async ({
        page,
      }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.waitForLoadState("networkidle");
        await page.getByTestId("welcome-filters-trigger").tap();
        const sheet = page.getByRole("dialog");
        await expect(sheet).toHaveAttribute("data-form", "sheet");
        const box = await sheet.boundingBox();
        expect(box?.x).toBe(0);
        expect(Math.round(box?.width ?? 0)).toBe(size.width);
        expect(Math.round((box?.y ?? 0) + (box?.height ?? 0))).toBe(
          size.height,
        );
        await shot(page, lang as Lang, name("05-filters"));
        await sheet.getByRole("button", { name: /^(Архив|Archive)$/ }).tap();
        await expect(page.getByTestId("welcome-filters-trigger")).toContainText(
          "1",
        );
        await page.getByTestId("welcome-filters-done").tap();
        await expect(page.getByRole("dialog")).toHaveCount(0);
        for (const own of USERS.anna.projects) {
          await expect(
            page.locator(`[data-project-card][aria-label="${own}"]`),
          ).toHaveCount(0);
        }
      });

      test("меню аккаунта: шторка, тема и язык", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.getByTestId("account-menu-trigger").tap();
        const menu = page.getByTestId("account-menu");
        await expect(menu).toHaveAttribute("data-form", "sheet");
        await shot(page, lang as Lang, name("06-account"));
        await page.getByTestId("account-menu-theme-light").tap();
        await expect(page.locator("html")).toHaveAttribute(
          "data-theme",
          "light",
        );
        await page.getByTestId("account-menu-theme-dark").tap();
        await expect(page.locator("html")).toHaveAttribute(
          "data-theme",
          "dark",
        );
        const other = lang === "ru" ? "en" : "ru";
        await page.getByTestId(`account-menu-lang-${other}`).tap();
        await expect(page.locator("html")).toHaveAttribute("lang", other);
      });

      test("диалог открывается шторкой, закрывается крестиком и по фону", async ({
        page,
      }) => {
        await loginOnPhone(page, USERS.anna.email);
        await page.waitForLoadState("networkidle");
        await page
          .getByRole("button", { name: /Импорт|Import/ })
          .first()
          .tap();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toHaveAttribute("data-form", "sheet");
        await shot(page, lang as Lang, name("07-import-sheet"));
        await dialog.getByRole("button", { name: /Закрыть|Close/ }).tap();
        await expect(page.getByRole("dialog")).toHaveCount(0);

        await page
          .getByRole("button", { name: /Импорт|Import/ })
          .first()
          .tap();
        await expect(page.getByRole("dialog")).toBeVisible();
        await page.touchscreen.tap(size.width / 2, 40);
        await expect(page.getByRole("dialog")).toHaveCount(0);
      });

      test("входящие, подключение к серверу и локальная версия помещаются в окно", async ({
        page,
      }) => {
        await loginOnPhone(page, USERS.anna.email);
        for (const path of ["/inbox", "/connect", "/local-studio"]) {
          await page.goto(path);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
        }
        await page.goto("/inbox");
        await shot(page, lang as Lang, name("08-inbox"));
      });
    });
  }
}

/** Первый проект Анны и его документ из шаблона: на стенде они есть у демо-пользователя. */
const openProjectApi = async (
  page: Page,
): Promise<{ projectId: string; userId: string }> => {
  const listing = await page.request.get("/api/v1/projects?limit=100");
  const items = ((await listing.json()) as { items: { id: string; name: string }[] }).items;
  const first = items[0];
  if (!first) throw new Error("у демо-пользователя нет проектов");
  const me = await page.request.get("/api/v1/session/bootstrap");
  const userId = ((await me.json()) as { user?: { id: string } }).user?.id ?? "me";
  return { projectId: first.id, userId };
};

const DOC = "project_proposal";
const tabBar = (page: Page) => page.locator(".activity-bar--tabs");
const tabButton = (page: Page, name: RegExp) => tabBar(page).getByRole("button", { name });

for (const lang of LANGS) {
  for (const size of SIZES) {
    test.describe(`Проект на телефоне ${String(size.width)} [${lang}]`, () => {
      test.use({
        locale: lang === "ru" ? "ru-RU" : "en-US",
        viewport: size,
        hasTouch: true,
        isMobile: true,
      });
      const name = (suffix: string): string => `mobile-${String(size.width)}-${suffix}`;
      const L = lang as Lang;

      test("нижняя панель вкладок переключает разделы, страница не шире окна", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId } = await openProjectApi(page);
        await page.goto(`/projects/${projectId}/documents`);
        await expect(tabBar(page)).toBeVisible();
        // Список документов открыт сразу: у обзора нет документа, и нужен выбор.
        await expect(page.locator(".workbench-sidebar.mobile-open")).toBeVisible();
        await expectNoHorizontalScroll(page);
        await shot(page, L, name("10-project-documents"));

        const sections: [RegExp, string][] = [
          [/Замечания|Issues/, "11-project-review"],
          [/Сдача|Submission/, "12-project-submit"],
          [/Файлы|Files/, "13-project-files"],
        ];
        for (const [label, file] of sections) {
          await tabButton(page, label).tap();
          await expect(tabButton(page, label)).toHaveAttribute("aria-current", "page");
          await expect(page.locator(".workbench-sidebar.mobile-open")).toBeVisible();
          await expectNoHorizontalScroll(page);
          await shot(page, L, name(file));
        }
        // Повторное нажатие на активную вкладку прячет панель.
        await tabButton(page, /Файлы|Files/).tap();
        await expect(page.locator(".workbench-sidebar.mobile-open")).toHaveCount(0);
      });

      test("«Ещё»: настройки проекта, история, агент", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId } = await openProjectApi(page);
        await page.goto(`/projects/${projectId}/documents/${DOC}`);
        await tabButton(page, /Ещё|More/).tap();
        const sheet = page.getByRole("dialog");
        await expect(sheet).toHaveAttribute("data-form", "sheet");
        await expect(page.getByTestId("activity-more").getByRole("button")).toHaveCount(4);
        await shot(page, L, name("14-project-more"));

        await page.getByTestId("activity-more-projectSettings").tap();
        await expect(page).toHaveURL(/\/project-settings/);
        // Оглавление разделов настроек открыто панелью, выбор раздела её закрывает.
        await expect(page.locator(".workbench-sidebar.mobile-open")).toBeVisible();
        await shot(page, L, name("15-project-settings"));
        await page.locator(".workbench-sidebar.mobile-open .panel-body").getByRole("button").nth(1).tap();
        await expect(page.locator(".workbench-sidebar.mobile-open")).toHaveCount(0);
        await expectNoHorizontalScroll(page);

        await tabButton(page, /Ещё|More/).tap();
        await page.getByTestId("activity-more-versions").tap();
        await expect(page).toHaveURL(/\/versions/);
        await expectNoHorizontalScroll(page);
        await shot(page, L, name("16-project-history"));

        await tabButton(page, /Ещё|More/).tap();
        await page.getByTestId("activity-more-agent").tap();
        const dock = page.locator(".chat-dock");
        await expect(dock).toBeVisible();
        const box = await dock.boundingBox();
        expect(Math.round(box?.width ?? 0)).toBe(size.width);
        expect(Math.round(box?.height ?? 0)).toBe(size.height);
        await shot(page, L, name("17-project-agent"));
        // Экранная клавиатура (iOS не уменьшает окно): useKeyboardInset пишет --kb-inset, агент поднимается над ней.
        await page.evaluate(() => {
          document.documentElement.style.setProperty("--kb-inset", "300px");
        });
        await expect
          .poll(async () => Math.round((await dock.boundingBox())?.height ?? 0))
          .toBe(size.height - 300);
        await page.evaluate(() => {
          document.documentElement.style.removeProperty("--kb-inset");
        });
        await dock.locator(".icon-btn").last().tap();
        await expect(dock).toHaveCount(0);
      });

      test("документ: превью и редактор переключаются, «Рядом» нет", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId } = await openProjectApi(page);
        await page.goto(`/projects/${projectId}/documents/${DOC}`);
        const tabs = page.getByRole("tablist");
        await expect(tabs.getByRole("tab")).toHaveCount(2);
        await expect(tabs.getByRole("tab", { name: /Рядом|Side/ })).toHaveCount(0);
        await expectNoHorizontalScroll(page);
        await tabs.getByRole("tab", { name: /Редактор|Editor/ }).tap();
        await expect(page.locator(".cm-content")).toBeVisible();
        await expectNoHorizontalScroll(page);
        await shot(page, L, name("18-project-editor"));
        await tabs.getByRole("tab", { name: /Превью|Preview/ }).tap();
        await expect(page.locator(".cm-content")).toHaveCount(0);
        for (const tab of ["checks", "compile", "history", "signatures"]) {
          await page.goto(`/projects/${projectId}/documents/${DOC}?tab=${tab}`);
          await page.waitForLoadState("networkidle");
          await expectNoHorizontalScroll(page);
        }
      });

      test("строка вкладок документа не шире экрана, выбранная вкладка видна", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId } = await openProjectApi(page);
        const row = page.locator(".document-workspace-header + .tabs");
        const scroller = row.locator(".tabs-scroll");
        const more = row.getByRole("button", { name: /Ещё действия|More actions/ });
        const within = async (
          locator: ReturnType<Page["locator"]>,
          box: { x: number; width: number },
          what: string,
        ): Promise<void> => {
          const rect = await locator.boundingBox();
          expect(rect, what).not.toBeNull();
          expect(rect?.x ?? -1, `${what}: левый край`).toBeGreaterThanOrEqual(box.x - 1);
          expect((rect?.x ?? 0) + (rect?.width ?? 0), `${what}: правый край`).toBeLessThanOrEqual(
            box.x + box.width + 1,
          );
        };
        for (const tab of [null, "checks", "compile", "history", "signatures"]) {
          const what = tab ?? "preview";
          await page.goto(`/projects/${projectId}/documents/${DOC}${tab ? `?tab=${tab}` : ""}`);
          await expect(row).toBeVisible();
          await within(row, { x: 0, width: size.width }, `${what}: строка вкладок`);
          // «Ещё действия» прижата справа и не уезжает вместе с вкладками.
          await within(more, { x: 0, width: size.width }, `${what}: «Ещё действия»`);
          // Выбранная вкладка (в том числе пришедшая из адреса) докручена в видимую часть строки.
          const box = await scroller.boundingBox();
          expect(box, `${what}: прокручиваемая часть`).not.toBeNull();
          await expect
            .poll(async () => {
              const rect = await scroller.locator("button.active").boundingBox();
              if (!rect || !box) return false;
              return rect.x >= box.x - 1 && rect.x + rect.width <= box.x + box.width + 1;
            })
            .toBe(true);
          // Вкладки за краем есть: край, за которым они, затухает (подсказка, что строка прокручивается).
          const hint = await scroller.evaluate((el) => ({
            overflow: el.scrollWidth > el.clientWidth + 1,
            edge:
              el.getAttribute("data-scroll-start") === "true" ||
              el.getAttribute("data-scroll-end") === "true",
            mask: getComputedStyle(el).maskImage,
          }));
          if (hint.overflow) {
            expect(hint.edge, `${what}: отмечен край прокрутки`).toBe(true);
            expect(hint.mask, `${what}: затухание края`).toContain("gradient");
          }
          await expectNoHorizontalScroll(page);
        }
        await shot(page, L, name("18a-document-tabs"));
      });

      test("редактор: шрифт 16 px, при вводе панели уходят, оглавление поверх текста", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId } = await openProjectApi(page);
        await page.goto(`/projects/${projectId}/documents/${DOC}?tab=source`);
        const content = page.locator(".cm-content");
        await expect(content).toBeVisible();
        const fontSize = await content.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
        expect(fontSize).toBeGreaterThanOrEqual(16);
        await expect(tabBar(page)).toBeVisible();
        await expect(page.locator(".titlebar")).toBeVisible();

        await content.tap();
        await expect(page.locator(".cm-editor.cm-focused")).toBeVisible();
        // Пока пишете, нижняя панель и шапка не отнимают высоту у текста.
        await expect(tabBar(page)).toBeHidden();
        await expect(page.locator(".titlebar")).toBeHidden();
        const before = await content.innerText();
        await page.keyboard.type("x");
        await expect.poll(async () => content.innerText()).not.toBe(before);
        await page.keyboard.press("Backspace");
        await expect.poll(async () => content.innerText()).toBe(before);

        // Панель инструментов прокручивается по горизонтали и не раздувает страницу.
        const toolbar = page.locator(".visual-format-toolbar");
        await expect(toolbar).toBeVisible();
        expect(await toolbar.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
        await expectNoHorizontalScroll(page);
      });

      test("люди в проекте, Студия и синхронизация в строке под шапкой", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId, userId } = await openProjectApi(page);
        await mockPeopleAndStudios(page, userId);
        await page.goto(`/projects/${projectId}/documents/${DOC}`);
        const row = page.getByTestId("titlebar-subrow");
        await expect(row).toBeVisible();
        const people = page.getByTestId("project-people");
        await expect(people).toBeVisible();
        await expectTouchTarget(page, people, "люди в проекте");
        await expectTouchTarget(page, page.getByTestId("studio-presence").locator("button"), "плашка Студии");
        await expectNoHorizontalScroll(page);
        await shot(page, L, name("19-project-header"));

        await people.tap();
        const list = page.getByTestId("people-list");
        await expect(list).toBeVisible();
        await expect(list.getByTestId("people-row")).toHaveCount(3);
        await expect(list.locator("xpath=ancestor::*[@data-form][1]")).toHaveAttribute("data-form", "sheet");
        await shot(page, L, name("20-project-people"));
        await page.keyboard.press("Escape");

        await page.getByTestId("studio-presence").locator("button").tap();
        await expect(page.getByRole("dialog", { name: /Студи|Studio/ })).toBeVisible();
        await shot(page, L, name("21-project-studios"));
        await page.keyboard.press("Escape");
        await expect(page.getByRole("dialog")).toHaveCount(0);
      });

      test("PDF по ширине экрана, масштаб кнопками и щипком", async ({ page, context }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId } = await openProjectApi(page);
        await mockBuiltPdf(page);
        await page.goto(`/projects/${projectId}/documents/${DOC}`);
        const zoom = page.getByLabel(/Масштаб в процентах|Zoom percent/);
        await expect(zoom).toBeVisible();
        const pageEl = page.locator("[data-page]").first();
        await expect(pageEl).toBeVisible();
        // Первый проект Анны зависит от прошедших сценариев; если его шаблон отстал, внизу висит уведомление
        // «Исправления шаблона», и на 360x740 нижний палец щипка попадал в него, а не в PDF.
        await closeToasts(page);
        const fitted = await pageEl.boundingBox();
        // Страница сразу по ширине окна, а не шире него.
        expect(fitted?.width ?? 0).toBeLessThanOrEqual(size.width);
        expect(fitted?.width ?? 0).toBeGreaterThan(size.width * 0.8);
        const fitPercent = Number(await zoom.inputValue());
        await shot(page, L, name("22-project-pdf"));

        // Панель PDF без прокрутки вбок: страницы и масштаб на виду, остальное в меню «Ещё».
        const toolbar = page.locator(".pdf-toolbar");
        expect(await toolbar.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
        await expect(page.getByTestId("pdf-toolbar-more")).toBeVisible();

        await page.getByRole("button", { name: /Увеличить|Zoom in/ }).tap();
        await expect.poll(async () => Number(await zoom.inputValue())).toBeGreaterThan(fitPercent);

        // Щипок двумя пальцами (CDP): масштаб растёт без увеличения всей страницы.
        const before = Number(await zoom.inputValue());
        const cdp = await context.newCDPSession(page);
        const area = await page.locator(".pdf-scroll").boundingBox();
        await cdp.send("Input.synthesizePinchGesture", {
          x: Math.round((area?.x ?? 0) + (area?.width ?? 0) / 2),
          y: Math.round((area?.y ?? 0) + (area?.height ?? 0) / 2),
          scaleFactor: 1.8,
          relativeSpeed: 400,
          gestureSourceType: "touch",
        });
        await expect.poll(async () => Number(await zoom.inputValue())).toBeGreaterThan(before);
        const visualScale = await page.evaluate(() => window.visualViewport?.scale ?? 1);
        expect(visualScale).toBe(1);
        await expectNoHorizontalScroll(page);
      });

      test("основные цели касания проекта не меньше 40 px", async ({ page }) => {
        await loginOnPhone(page, USERS.anna.email);
        const { projectId } = await openProjectApi(page);
        const small = async (): Promise<string[]> =>
          page.evaluate((min) => {
            const out: string[] = [];
            const nodes = document.querySelectorAll("button, a[href], input, select, textarea, [role=button], [role=tab]");
            for (const el of nodes) {
              const rect = el.getBoundingClientRect();
              if (rect.width === 0 || rect.height === 0 || el.closest("[aria-hidden=true]")) continue;
              if (rect.top >= innerHeight || rect.bottom <= 0) continue;
              if (el instanceof HTMLInputElement && ["checkbox", "radio"].includes(el.type)) continue;
              // Текстовая ссылка внутри абзаца - не кнопка.
              if (el instanceof HTMLAnchorElement && getComputedStyle(el).display === "inline") continue;
              if (Math.min(rect.width, rect.height) < min - 0.5) {
                out.push(`${el.tagName.toLowerCase()} ${String(Math.round(rect.width))}x${String(Math.round(rect.height))} ${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30)}`);
              }
            }
            return out;
          }, MIN_TOUCH);
        await page.goto(`/projects/${projectId}/documents/${DOC}`);
        await page.waitForLoadState("networkidle");
        expect(await small()).toEqual([]);
        for (const label of [/Замечания|Issues/, /Сдача|Submission/, /Файлы|Files/]) {
          await tabButton(page, label).tap();
          expect(await small(), String(label)).toEqual([]);
        }
        await tabButton(page, /Ещё|More/).tap();
        expect(await small()).toEqual([]);
      });
    });
  }
}

test.describe("Планшет 820x1180", () => {
  test.use({
    viewport: { width: 820, height: 1180 },
    hasTouch: true,
    isMobile: true,
  });

  test("список проектов остаётся десктопным, окно остаётся окном", async ({
    page,
  }) => {
    await loginOnPhone(page, USERS.anna.email);
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("welcome-filters-trigger")).toHaveCount(0);
    await expectNoHorizontalScroll(page);
    await page
      .getByRole("button", { name: /Импорт|Import/ })
      .first()
      .click();
    await expect(page.getByRole("dialog")).toHaveAttribute(
      "data-form",
      "dialog",
    );
  });
});
