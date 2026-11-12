import { demoError, demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRequest, DemoRoute } from "@shared/api/demo";
import type {
  PdfPlace,
  PdfRect,
  ReviewComment,
  ReviewThread,
} from "@entities/review";
import { effectiveRole } from "./projectAccess";
import type { ServerDemoWorld } from "./world";

// Ревью-комментарии в серверном демо (stage5-review-realtime.md, раздел 2): треды в
// памяти вкладки, комментарии из превью PDF (2.4) с «исходником» пояснительной
// записки. Выделение, текст которого есть в DEMO_SOURCE, становится тредом по
// исходнику, остальное (титул, колонтитулы) тредом к месту в PDF.

const DOC_ID = "vkr";
const PDF_PATH = "vkr/vkr.pdf";
const SOURCE_PATH = "vkr/chapters/intro.tex";
const BUILD_SHA = "demo-build-2";

/** Текст «главы» демо: те же абзацы лежат в PDF, который демо отдаёт превью. */
export const DEMO_SOURCE = `\\chapter{Введение}

Выпускная квалификационная работа посвящена автоматизации нормоконтроля
учебных документов. Студент пишет текст в \\LaTeX, а Студия собирает PDF по
шаблону факультета и проверяет оформление по ГОСТ~7.32--2017.

Научный руководитель и рецензент читают готовый PDF, а не исходник. Поэтому
замечания удобно оставлять прямо в превью: выделить фрагмент и нажать
<<Комментировать>>.

\\section{Цель и задачи}

Цель работы: сократить время согласования документа между студентом и
научным руководителем.
`;

type Store = { threads: ReviewThread[]; places: Map<string, PdfPlace> };
const stores = new WeakMap<ServerDemoWorld, Store>();

const at = (minutesAgo: number): string =>
  new Date(Date.now() - minutesAgo * 60_000).toISOString();

const comment = (
  id: string,
  author: [string, string],
  body: string,
  minutesAgo: number,
): ReviewComment => ({
  id,
  author_id: author[0],
  author_name: author[1],
  body,
  mentions: [],
  created_at: at(minutesAgo),
  edited_at: null,
});

const PETROV: [string, string] = ["u_demo_petrov", "Петров И. С."];
const RITA: [string, string] = ["u_demo_rita", "Рита Соколова"];

const seed = (): Store => {
  const quote = "сократить время согласования документа";
  const start = DEMO_SOURCE.indexOf(quote);
  const textThread: ReviewThread = {
    id: "rvt_demo_text",
    path: SOURCE_PATH,
    anchor: {
      kind: "text",
      quote,
      prefix: DEMO_SOURCE.slice(Math.max(0, start - 40), start),
      suffix: DEMO_SOURCE.slice(
        start + quote.length,
        start + quote.length + 40,
      ),
      start,
      end: start + quote.length,
    },
    status: "open",
    created_by: PETROV[0],
    created_by_name: PETROV[1],
    created_at: at(95),
    updated_at: at(40),
    resolved_by_name: null,
    resolved_at: null,
    comments: [
      comment(
        "rvc_demo_1",
        PETROV,
        "Насколько сократить? Добавьте измеримую цель.",
        95,
      ),
      comment(
        "rvc_demo_2",
        RITA,
        "Поддерживаю, без числа цель не проверить.",
        40,
      ),
    ],
  };
  const pdfThread: ReviewThread = {
    id: "rvt_demo_pdf",
    path: PDF_PATH,
    anchor: {
      kind: "pdf",
      doc_id: DOC_ID,
      page: 1,
      rects: [{ x: 160, y: 120, width: 280, height: 18 }],
      text: "Факультет компьютерных наук",
      build_sha: BUILD_SHA,
    },
    status: "open",
    created_by: RITA[0],
    created_by_name: RITA[1],
    created_at: at(30),
    updated_at: at(30),
    resolved_by_name: null,
    resolved_at: null,
    comments: [
      comment(
        "rvc_demo_3",
        RITA,
        "На титуле нужно полное название факультета.",
        30,
      ),
    ],
  };
  const movedThread: ReviewThread = {
    id: "rvt_demo_moved",
    path: PDF_PATH,
    anchor: {
      kind: "pdf",
      doc_id: DOC_ID,
      page: 2,
      rects: [{ x: 85, y: 410, width: 300, height: 14 }],
      text: "Таблица 1 Сравнение подходов",
      build_sha: "demo-build-1",
    },
    status: "open",
    created_by: PETROV[0],
    created_by_name: PETROV[1],
    created_at: at(600),
    updated_at: at(600),
    resolved_by_name: null,
    resolved_at: null,
    comments: [
      comment("rvc_demo_4", PETROV, "Подпишите столбцы таблицы.", 600),
    ],
  };
  const places = new Map<string, PdfPlace>([
    [
      textThread.id,
      {
        page: 1,
        rects: [{ x: 72, y: 600, width: 450, height: 16 }],
        text: quote,
        exact: false,
      },
    ],
    [
      pdfThread.id,
      {
        page: 1,
        rects: pdfThread.anchor.kind === "pdf" ? pdfThread.anchor.rects : [],
        text: "Факультет компьютерных наук",
        exact: false,
      },
    ],
    [
      movedThread.id,
      {
        page: 2,
        rects: [{ x: 85, y: 410, width: 300, height: 14 }],
        text: "Таблица 1 Сравнение подходов",
        exact: false,
      },
    ],
  ]);
  return { threads: [textThread, pdfThread, movedThread], places };
};

const storeOf = (world: ServerDemoWorld): Store => {
  let store = stores.get(world);
  if (!store) {
    store = seed();
    stores.set(world, store);
  }
  return store;
};

const fold = (text: string): string =>
  text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]/gu, "");

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const bodyOf = (req: DemoRequest): Record<string, unknown> =>
  (req.body ?? {}) as Record<string, unknown>;

const author = (world: ServerDemoWorld): [string | null, string] => {
  const user = world.bootstrap.user;
  if (user) return [user.id, user.name || user.email];
  return [null, `Гость: ${world.bootstrap.guest?.name ?? "без имени"}`];
};

export const createReviewRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const roleIn = (projectId: string) => {
    const world = getWorld();
    const project = world.projects.find((p) => p.summary.id === projectId);
    return project
      ? effectiveRole(world, project, world.bootstrap.user?.id)
      : null;
  };
  const touch = (thread: ReviewThread): void => {
    thread.updated_at = new Date().toISOString();
  };
  const find = (id: string) =>
    storeOf(getWorld()).threads.find((x) => x.id === id);

  const newThread = (
    path: string,
    anchor: ReviewThread["anchor"],
    body: string,
  ): ReviewThread => {
    const world = getWorld();
    const [id, name] = author(world);
    const threadId = `rvt_demo_${String(Date.now())}`;
    const now = new Date().toISOString();
    return {
      id: threadId,
      path,
      anchor,
      status: "open",
      created_by: id,
      created_by_name: name,
      created_at: now,
      updated_at: now,
      resolved_by_name: null,
      resolved_at: null,
      comments: [
        {
          id: `rvc_demo_${String(Date.now())}`,
          author_id: id,
          author_name: name,
          body,
          mentions: [],
          created_at: now,
          edited_at: null,
        },
      ],
    };
  };

  return [
    {
      method: "GET",
      pattern: "/projects/:projectId/review/documents/:docId",
      handler: (req) => {
        const role = roleIn(req.params.projectId ?? "");
        if (!role) return demoError(404, "not_found", "Not found");
        if (role === "reader") return demoError(403, "forbidden", "Forbidden");
        if (req.params.docId !== DOC_ID)
          return demoJson({ build_sha: null, items: [] });
        const store = storeOf(getWorld());
        return demoJson({
          build_sha: BUILD_SHA,
          items: store.threads.map((thread) => ({
            thread,
            place: store.places.get(thread.id) ?? null,
          })),
        });
      },
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/review/pdf-threads",
      handler: (req) => {
        const role = roleIn(req.params.projectId ?? "");
        if (!role) return demoError(404, "not_found", "Not found");
        if (role === "reader") return demoError(403, "forbidden", "Forbidden");
        const b = bodyOf(req);
        const text = str(b.text).trim();
        const body = str(b.body).trim();
        const rects = (b.rects ?? []) as PdfRect[];
        const page = Number(b.page ?? 1);
        if (!body) return demoError(422, "empty_body", "Empty body");
        if (!text) return demoError(422, "empty_quote", "Empty quote");
        if (rects.length === 0)
          return demoError(422, "bad_rects", "Select the text again");
        const store = storeOf(getWorld());
        // «Исходник» демо: ищем выделение по буквам и цифрам, как сервер.
        const needle = fold(text);
        const words = DEMO_SOURCE.split(/(\s+)/);
        let found: { start: number; end: number } | null = null;
        if (needle.length >= 4 && fold(DEMO_SOURCE).includes(needle)) {
          let offset = 0;
          for (let i = 0; i < words.length && !found; i++) {
            let acc = "";
            let end = offset;
            for (let j = i; j < words.length; j++) {
              acc += fold(words[j] ?? "");
              end += (words[j] ?? "").length;
              if (acc.startsWith(needle) || needle.startsWith(acc)) {
                if (acc.length >= needle.length) {
                  found = { start: offset, end };
                  break;
                }
              } else break;
            }
            offset += (words[i] ?? "").length;
          }
        }
        let thread: ReviewThread;
        if (found) {
          const quote = DEMO_SOURCE.slice(found.start, found.end);
          thread = newThread(
            SOURCE_PATH,
            {
              kind: "text",
              quote,
              prefix: DEMO_SOURCE.slice(
                Math.max(0, found.start - 40),
                found.start,
              ),
              suffix: DEMO_SOURCE.slice(found.end, found.end + 40),
              start: found.start,
              end: found.end,
            },
            body,
          );
        } else {
          thread = newThread(
            PDF_PATH,
            {
              kind: "pdf",
              doc_id: str(b.doc_id) || DOC_ID,
              page,
              rects,
              text,
              build_sha: BUILD_SHA,
            },
            body,
          );
        }
        store.threads.unshift(thread);
        store.places.set(thread.id, {
          page,
          rects,
          text,
          exact: !found,
        });
        return demoJson(thread, 201);
      },
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/review/threads",
      handler: (req) => {
        if (!roleIn(req.params.projectId ?? ""))
          return demoError(404, "not_found", "Not found");
        const raw = req.query.path;
        const path = typeof raw === "string" ? raw : null;
        const items = storeOf(getWorld()).threads.filter(
          (x) => path === null || x.path === path,
        );
        return demoJson({ items });
      },
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/review/threads/:threadId/comments",
      handler: (req) => {
        const thread = find(req.params.threadId ?? "");
        if (!thread) return demoError(404, "not_found", "Thread not found");
        const body = str(bodyOf(req).body).trim();
        if (!body) return demoError(422, "empty_body", "Empty body");
        const [id, name] = author(getWorld());
        thread.comments.push({
          id: `rvc_demo_${String(Date.now())}`,
          author_id: id,
          author_name: name,
          body,
          mentions: [],
          created_at: new Date().toISOString(),
          edited_at: null,
        });
        touch(thread);
        return demoJson(thread, 201);
      },
    },
    {
      method: "PUT",
      pattern: "/projects/:projectId/review/threads/:threadId/status",
      handler: (req) => {
        const thread = find(req.params.threadId ?? "");
        if (!thread) return demoError(404, "not_found", "Thread not found");
        const status = bodyOf(req).status === "resolved" ? "resolved" : "open";
        const [, name] = author(getWorld());
        thread.status = status;
        thread.resolved_by_name = status === "resolved" ? name : null;
        thread.resolved_at =
          status === "resolved" ? new Date().toISOString() : null;
        touch(thread);
        return demoJson(thread);
      },
    },
    {
      method: "DELETE",
      pattern: "/projects/:projectId/review/comments/:commentId",
      handler: (req) => {
        const store = storeOf(getWorld());
        const id = req.params.commentId ?? "";
        const thread = store.threads.find((x) =>
          x.comments.some((c) => c.id === id),
        );
        if (!thread) return demoError(404, "not_found", "Not found");
        if (thread.comments[0]?.id === id)
          store.threads = store.threads.filter((x) => x !== thread);
        else thread.comments = thread.comments.filter((c) => c.id !== id);
        return demoNoContent();
      },
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/review/mentions",
      handler: () =>
        demoJson({
          items: [
            {
              user_id: PETROV[0],
              name: PETROV[1],
              detail: "научный руководитель",
            },
            { user_id: RITA[0], name: RITA[1], detail: "рецензент" },
          ],
        }),
    },
  ];
};
