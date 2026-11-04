import type { Page, Route } from "@playwright/test";

/**
 * Подмены для телефонных сценариев: на стенде server-lite один пользователь и нет раннера,
 * поэтому чужих людей в проекте, подключённую Студию и собранный PDF берём из заглушек.
 */

/** Небольшой настоящий PDF из трёх страниц: pdf.js читает его без ошибок. */
export const samplePdf = (): Buffer => {
  const objects: string[] = [];
  const pageCount = 3;
  objects.push("<< /Type /Catalog /Pages 2 0 R >>");
  const kids = Array.from({ length: pageCount }, (_, i) => `${String(4 + i * 2)} 0 R`).join(" ");
  objects.push(`<< /Type /Pages /Kids [${kids}] /Count ${String(pageCount)} >>`);
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  for (let i = 0; i < pageCount; i += 1) {
    const stream = `BT /F1 14 Tf 60 780 Td (Sample page ${String(i + 1)}) Tj ET`;
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents ${String(5 + i * 2)} 0 R >>`,
    );
    objects.push(`<< /Length ${String(stream.length)} >>\nstream\n${stream}\nendstream`);
  }
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${String(index + 1)} 0 obj\n${object}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${String(objects.length + 1)}\n0000000000 65535 f \n`;
  for (const offset of offsets) body += `${String(offset).padStart(10, "0")} 00000 n \n`;
  body += `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\nstartxref\n${String(xref)}\n%%EOF\n`;
  return Buffer.from(body, "latin1");
};

const iso = (): string => new Date().toISOString();

/** Двое других людей в проекте и одна локальная Студия: шапка проекта показывает аватары и плашку Студии. */
export const mockPeopleAndStudios = async (page: Page, myId: string): Promise<void> => {
  await page.route(/\/projects\/[^/]+\/presence$/, async (route: Route) => {
    if (route.request().method() !== "POST") return route.continue();
    const person = (
      user_id: string,
      name: string,
      initials: string,
      color: string,
      me: boolean,
    ) => ({
      user_id,
      name,
      initials,
      color,
      role: me ? "owner" : "editor",
      me,
      activity: me ? "viewing" : "editing",
      doc_id: null,
      channels: ["web"],
      seen_at: iso(),
    });
    await route.fulfill({
      json: {
        interval_s: 10,
        online_window_s: 30,
        total: 3,
        people: [
          person(myId, "Анна Иванова", "АИ", "#3b82f6", true),
          person("b", "Борис Петров", "БП", "#22c55e", false),
          person("v", "Victor Smith", "VS", "#f59e0b", false),
        ],
      },
    });
  });
  await page.route(/\/projects\/[^/]+\/studios$/, async (route: Route) => {
    await route.fulfill({
      json: {
        online_window_s: 30,
        others: [],
        mine: [
          {
            id: "dev1",
            name: "MacBook Анны",
            version: "0.6.0",
            os: "macos",
            presence: "online",
            last_seen_at: iso(),
            activity: "idle",
            projects_count: 1,
            runner: null,
            ai: { state: "no_provider", endpoints: [] },
            project: {
              sync: "synced",
              ahead: 0,
              behind: 0,
              last_sync_at: iso(),
              auto_sync: true,
              pdf: null,
            },
          },
        ],
      },
    });
  });
};

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

const markBuilt = (value: Json): Json => {
  if (Array.isArray(value)) return value.map((item) => markBuilt(item as Json));
  if (value !== null && typeof value === "object") {
    const copy: Record<string, unknown> = { ...value };
    if ("status" in copy && "id" in copy) {
      copy.status = "ok";
      copy.output_file = copy.output_file ?? "project_proposal/project_proposal.pdf";
    }
    for (const key of Object.keys(copy)) copy[key] = markBuilt(copy[key] as Json);
    return copy;
  }
  return value;
};

/** Документы «собраны», PDF отдаётся образцом: раннера на стенде нет, а превью без PDF не проверить. */
export const mockBuiltPdf = async (page: Page): Promise<void> => {
  await page.route(
    /\/api\/v1\/projects\/[^/]+\/documents(\/[^/?]+)?(\?.*)?$/,
    async (route: Route) => {
      if (route.request().method() !== "GET") return route.continue();
      const response = await route.fetch();
      await route.fulfill({ response, json: markBuilt((await response.json()) as Json) });
    },
  );
  const pdf = samplePdf();
  await page.route(/\.pdf(\?.*)?$/, (route: Route) =>
    route.fulfill({ body: pdf, contentType: "application/pdf" }),
  );
};
