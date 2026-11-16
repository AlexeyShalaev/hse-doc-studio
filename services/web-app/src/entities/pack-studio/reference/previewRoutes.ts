import { demoError, demoJson, type DemoRoute } from "@shared/api/demo";
import { StartPackPreviewRequestSchema } from "../api/schemas";
import type { PackPreviewBuild } from "../api/schemas";
import {
  COURSEWORK_SCENARIOS,
  VKR_PREVIEW_OPTIONS,
  previewBuildReference,
} from "./fixtures";

// Подмена эндпоинтов предпросмотра «на эталонах» (срез F12): экран «Результат» в разработке
// собирает документ без сервера. Сборка проходит те же состояния, что настоящая: в очереди, идёт,
// готова; PDF подмена не отдаёт (его грузит просмотрщик напрямую), поэтому в окне предпросмотра
// видно окружение сборки, а не страницы. Состояние живёт в памяти страницы.

const VERSION =
  "/pack-studio/workspaces/:id/versions/:pack/:template/:version/preview";
const BUILD = "/pack-studio/workspaces/:id/previews/:buildId";

type Entry = { build: PackPreviewBuild; polls: number };
const builds = new Map<string, Entry>();
let counter = 0;

/** Для тестов и галереи: забыть собранное. */
export const resetPreviewReference = (): void => {
  builds.clear();
  counter = 0;
};

const fileNameOf = (document: string, variant: string | null): string =>
  `${document}${variant ? `-${variant}` : ""}.pdf`;

/** Как подмена ведёт себя сейчас: отдать запрос настоящему серверу или собирать «на эталонах». */
export type PreviewReferenceMode = {
  server: () => boolean;
  failing: () => boolean;
};

export const previewReferenceRoutes = (
  mode: PreviewReferenceMode,
): DemoRoute[] => [
  {
    method: "GET",
    pattern: VERSION,
    handler: async (req) => {
      if (mode.server()) {
        return (await req.forward()) as never;
      }
      const { id = "", pack = "", template = "", version = "" } = req.params;
      return demoJson({
        ...VKR_PREVIEW_OPTIONS,
        workspace_id: id,
        pack,
        template,
        version,
      });
    },
  },
  {
    method: "POST",
    pattern: VERSION,
    handler: async (req) => {
      if (mode.server()) {
        return (await req.forward()) as never;
      }
      const parsed = StartPackPreviewRequestSchema.safeParse(req.body);
      if (!parsed.success) {
        return demoError(422, "model_invalid", "Тело запроса не по схеме.");
      }
      const body = parsed.data;
      const document = body.documents[0] ?? "";
      const doc = VKR_PREVIEW_OPTIONS.documents.find((d) => d.id === document);
      if (!doc) {
        return demoError(400, "preview_invalid", "Документа нет.", {
          field: "document",
          value: document,
        });
      }
      const scenario = body.scenario
        ? COURSEWORK_SCENARIOS.scenarios.find((e) => e.id === body.scenario)
        : undefined;
      if (body.scenario && !scenario?.scenario) {
        return demoError(404, "scenario_not_found", "Сценария нет.", {
          scenario: body.scenario,
        });
      }
      const variant = body.variant ?? doc.default_variant ?? null;
      counter += 1;
      const failing = mode.failing();
      const base = previewBuildReference(failing ? "build_failed" : "queued");
      const build: PackPreviewBuild = {
        ...base,
        id: `ref-build-${String(counter)}`,
        workspace_id: req.params.id ?? "",
        pack: req.params.pack ?? "",
        template: req.params.template ?? "",
        version: req.params.version ?? "",
        document,
        example: body.example ?? scenario?.scenario?.example ?? "auto:normal",
        combination: {
          ...(scenario?.scenario?.inputs ?? {}),
          ...body.combination,
        },
        status: failing ? "failed" : "queued",
        variant,
        file_name: fileNameOf(document, variant),
        scenario: body.scenario ?? null,
        scenario_inputs: scenario?.scenario?.inputs ?? {},
      };
      builds.set(build.id, { build, polls: 0 });
      return demoJson({ builds: [build] });
    },
  },
  {
    method: "GET",
    pattern: BUILD,
    handler: async (req) => {
      if (mode.server()) {
        return (await req.forward()) as never;
      }
      const entry = builds.get(req.params.buildId ?? "");
      if (!entry) return demoError(404, "preview_not_found", "Сборки нет.");
      if (entry.build.status === "queued" || entry.build.status === "running") {
        entry.polls += 1;
        const succeeded = previewBuildReference("succeeded");
        entry.build =
          entry.polls === 1
            ? { ...entry.build, status: "running" }
            : { ...entry.build, status: "succeeded", pages: succeeded.pages };
      }
      return demoJson(entry.build);
    },
  },
  {
    method: "DELETE",
    pattern: BUILD,
    handler: async (req) => {
      if (mode.server()) {
        return (await req.forward()) as never;
      }
      const entry = builds.get(req.params.buildId ?? "");
      if (!entry) return demoError(404, "preview_not_found", "Сборки нет.");
      if (entry.build.status === "queued" || entry.build.status === "running") {
        entry.build = { ...entry.build, status: "cancelled" };
      }
      return demoJson(entry.build);
    },
  },
  {
    method: "GET",
    pattern: `${BUILD}/log`,
    handler: async (req) => {
      if (mode.server()) {
        return (await req.forward()) as never;
      }
      return { status: 200, data: "[reference] журнал сборки на эталонах\n" };
    },
  },
];
