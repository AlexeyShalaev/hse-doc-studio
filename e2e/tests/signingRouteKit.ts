import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { crc32, deflateSync, inflateSync } from "node:zlib";
import {
  expect,
  request as pwRequest,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { Client, type Json } from "./stack";

/**
 * Общее для e2e маршрута подписания на стенде server-lite с раннером поддельного TeX (make e2e-signing-route):
 * люди и проекты через API, сборка, маршрут через API, страница подписанта. Берут signing-route.spec.ts (E1) и
 * signing-snapshot.spec.ts (E2). Модуль один на воркер, поэтому RUN общий: почты людей у каждого файла свои.
 */
export const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:8100";
export const ORIGIN = new URL(baseURL).origin;
export const RUN = Date.now().toString(36);
export const PASSWORD = `Sr-${RUN}-passw0rd`;
export const PACK = {
  pack_id: "hse-cs-sse",
  template_id: "coursework",
  version: "2026.1.3",
};
export const PROFILE = "topic-approval";
export const PROPOSAL = "project_proposal";
export const APPLICATION = "topic_application";
export const APPLICATION_TEX = "topic_application/topic_application.tex";
export const APPLICATION_PDF = "topic_application/topic_application.pdf";
/** Отправлять маршрут заново можно не чаще раза в минуту (SEND_INTERVAL в use_cases/signing_route/author.py). */
export const RESEND_INTERVAL_MS = 61_000;


export type Person = { name: string; email: string };
export type Member = Person & { client: Client; id: string; context: BrowserContext };

export type Participant = {
  id: string;
  persona: string;
  user_id: string | null;
  invitation_id: string | null;
  name: string | null;
  membership: string;
  method: string | null;
  state: string;
  next_action: string;
  approved_at: string | null;
};
export type Route = {
  id: string;
  status: string;
  phase: string | null;
  round: number;
  current_step: number | null;
  stop_reason: string | null;
  sent_at: string | null;
  docs: {
    doc_id: string;
    frozen: boolean;
    slots: {
      slot_id: string;
      status: string;
      participant_id: string | null;
      /** Необязательна на точке маршрута и добавлена сверх точки (13.6). */
      optional?: boolean;
      extra?: boolean;
    }[];
    /** Версия на подписи (12.9): null у черновика, после отмены и у маршрута 0.20.0 без переноса. */
    sent: { sha256: string; at: string; round: number } | null;
    /** Рабочая сборка ушла от версии на подписи. */
    changed: boolean;
  }[];
  steps: Participant[][];
  events: { kind: string; round: number; comment: string | null }[];
  changed_docs: string[];
};
export type Preview = {
  can_send: boolean;
  docs: { doc_id: string; built: boolean; token: string | null }[];
  blockers: { code: string; doc_id: string | null; slot_id: string | null }[];
};

export const log = (...parts: unknown[]): void => {
  console.log(`[sr ${new Date().toISOString().slice(11, 19)}]`, ...parts);
};

export const required = (name: string): string => {
  const value = process.env[name];
  if (!value)
    throw new Error(
      `${name} не задан: запускайте через make e2e-signing-route (пароль админа из server-lite/.env)`,
    );
  return value;
};

export const sha256 = (data: Buffer): string =>
  createHash("sha256").update(data).digest("hex");

// ---------------------------------------------------------------- картинка подписи

/** PNG RGBA без фона с росчерком: картинка подписи для загрузки (как скан подписи с удалённым фоном). */
export const signaturePng = (): Buffer => {
  const width = 240;
  const height = 80;
  const rows: Buffer[] = [];
  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width * 4);
    for (let x = 0; x < width; x += 1) {
      const curve = 40 + Math.round(22 * Math.sin(x / 18));
      if (Math.abs(y - curve) <= 2 && x > 12 && x < width - 12)
        row.writeUInt32BE(0x1a2a6cff, 1 + x * 4);
    }
    rows.push(row);
  }
  const chunk = (type: string, data: Buffer): Buffer => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, "ascii");
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])) >>> 0, 0);
    return Buffer.concat([head, data, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.writeUInt8(8, 8); // глубина
  ihdr.writeUInt8(6, 9); // RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
};

// ---------------------------------------------------------------- OpenPGP академрука

/**
 * Ключ и подписи академрука делает настоящий gpg хоста (на раннерах GitHub он есть): так подписывает человек,
 * у которого ключ только на своём компьютере. Каталог ключей короткий, иначе сокет gpg-agent не помещается в путь.
 */
export class Gpg {
  readonly home: string;

  constructor(private readonly uid: string) {
    this.home = mkdtempSync(join(existsSync("/tmp") ? "/tmp" : tmpdir(), "sr-gpg-"));
    this.run(
      "--pinentry-mode",
      "loopback",
      "--passphrase",
      "",
      "--quick-gen-key",
      uid,
      "ed25519",
      "sign",
      "never",
    );
  }

  private run(...args: string[]): Buffer {
    return execFileSync("gpg", ["--batch", "--homedir", this.home, ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });
  }

  publicKey(): Buffer {
    return this.run("--armor", "--export", this.uid.replace(/^.*<|>$/g, ""));
  }

  /** Открепленная подпись .asc над байтами файла. */
  detachSign(file: string): Buffer {
    return this.run(
      "--pinentry-mode",
      "loopback",
      "--passphrase",
      "",
      "--armor",
      "--detach-sign",
      "--output",
      "-",
      file,
    );
  }

  dispose(): void {
    try {
      execFileSync("gpgconf", ["--homedir", this.home, "--kill", "gpg-agent"], {
        stdio: "ignore",
      });
    } catch {
      // gpgconf может не быть: агент уйдёт сам вместе с каталогом.
    }
    rmSync(this.home, { recursive: true, force: true });
  }
}

// ---------------------------------------------------------------- люди и проекты

export const newClient = async (): Promise<Client> =>
  new Client(await pwRequest.newContext({ baseURL }), ORIGIN);

export const register = async (
  admin: Client,
  browser: Browser,
  who: Person,
): Promise<Member> => {
  const invitation = await admin.json<{ link: string }>(
    await admin.post("/api/admin/invitations", {
      email: who.email,
      ttl_days: null,
    }),
    201,
  );
  // Клиент API и браузер человека делят одну сессию: запросы контекста и его страницы держат общие cookie, вход
  // один на человека. Регистрация и вход идут в лимит входа по IP (AUTH_IP), а все люди стенда приходят с одного
  // адреса: второй вход на человека съедал этот лимит, и вход проекта signing-route ловил 429.
  const context = await browser.newContext({
    baseURL,
    locale: "ru-RU",
    viewport: { width: 1440, height: 960 },
  });
  const client = new Client(context.request, ORIGIN);
  await client.json(
    await client.post("/api/v1/auth/register", {
      email: who.email,
      name: who.name,
      password: PASSWORD,
      invitation_token: invitation.link.split("/invite/")[1],
    }),
    200,
  );
  const user = await client.login(who.email, PASSWORD);
  // «Скопировать ссылку» кладёт адрес в буфер обмена.
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: ORIGIN,
  });
  return { ...who, client, id: String(user.id), context };
};

/** Проект студента с научруком и академруком: приглашения с персонами, оба принимают. */
export const createProject = async (
  student: Member,
  name: string,
  signers: { member: Member; persona: string }[],
): Promise<string> => {
  const project = await student.client.json(
    await student.client.post("/api/v1/projects", {
      name,
      ...PACK,
      lang: "ru",
      authors: [{ name: student.name }],
    }),
    201,
  );
  const id = String(project.id);
  for (const { member, persona } of signers) {
    const created = await student.client.json<{ invitation: { id: string } }>(
      await student.client.post(`/api/v1/projects/${id}/invitations`, {
        email: member.email,
        role: "reviewer",
        persona,
      }),
      201,
    );
    await member.client.json(
      await member.client.post(
        `/api/v1/account/invitations/${created.invitation.id}/accept`,
      ),
      200,
    );
  }
  return id;
};

export const compile = async (
  client: Client,
  projectId: string,
  docId: string,
): Promise<void> => {
  const started = await client.json<{ compile_id: string }>(
    await client.post(`/api/v1/projects/${projectId}/documents/${docId}/compile`),
    202,
  );
  await waitCompiled(client, projectId, docId, started.compile_id);
};

export const waitCompiled = async (
  client: Client,
  projectId: string,
  docId: string,
  compileId: string,
): Promise<void> => {
  await expect
    .poll(
      async () =>
        String(
          (
            await client.json<Json>(
              await client.get(
                `/api/v1/projects/${projectId}/documents/${docId}/compiles/${compileId}`,
              ),
              200,
            )
          ).status,
        ),
      { timeout: 60_000, intervals: [500, 1_000] },
    )
    .toBe("success");
};

export const fileBytes = async (
  client: Client,
  projectId: string,
  path: string,
): Promise<Buffer> => {
  const res = await client.get(`/api/v1/projects/${projectId}/files/${path}`);
  expect(res.status(), path).toBe(200);
  return res.body();
};

/** Правка исходника мимо интерфейса: строка-комментарий в конце, PDF после сборки другой. */
export const editSource = async (
  client: Client,
  projectId: string,
  path: string,
  note: string,
): Promise<void> => {
  const source = (await fileBytes(client, projectId, path)).toString("utf8");
  const res = await client.putText(
    `/api/v1/projects/${projectId}/files/${path}`,
    `${source}\n% ${note}\n`,
  );
  expect(res.status(), await res.text()).toBe(204);
};

/** Правка исходника заявления. */
export const editApplication = async (
  client: Client,
  projectId: string,
  note: string,
): Promise<void> => editSource(client, projectId, APPLICATION_TEX, note);

// ---------------------------------------------------------------- маршрут через API

export const routeOf = async (
  client: Client,
  projectId: string,
  routeId: string,
): Promise<Route> =>
  client.json<Route>(
    await client.get(`/api/v1/projects/${projectId}/signing-routes/${routeId}`),
    200,
  );

export const person = (route: Route, persona: string): Participant => {
  const found = route.steps.flat().find((p) => p.persona === persona);
  if (!found) throw new Error(`в маршруте нет ${persona}: ${JSON.stringify(route.steps)}`);
  return found;
};

/** Шаги маршрута как список персон: [[author], [supervisor], ...]. */
export const order = (route: Route): string[][] =>
  route.steps.map((step) => step.map((p) => p.persona));

export const uploadPng = async (
  client: Client,
  url: string,
  extra: Record<string, string> = {},
): Promise<Json> =>
  client.json<Json>(
    await client.postForm(url, {
      file: { name: "signature.png", mimeType: "image/png", buffer: signaturePng() },
      ...extra,
    }),
    200,
  );

/**
 * Маршрут точки через API, как его отправил бы редактор: документы собраны, академрук добавлен необязательным
 * слотом заявления, все подписи размещены, картинка автора загружена, отправлен. Возвращает id маршрута.
 */
export const sendRouteViaApi = async (
  student: Member,
  projectId: string,
): Promise<string> => {
  const client = student.client;
  await compile(client, projectId, PROPOSAL);
  await compile(client, projectId, APPLICATION);
  const draft = await client.json<Route>(
    await client.post(`/api/v1/projects/${projectId}/signing-routes`, {
      profile_id: PROFILE,
    }),
    201,
  );
  const steps = draft.steps.map((step) =>
    step.map((p) => ({
      id: p.id,
      persona: p.persona,
      user_id: p.user_id,
      invitation_id: p.invitation_id,
    })),
  );
  const route = await client.json<Route>(
    await client.put(`/api/v1/projects/${projectId}/signing-routes/${draft.id}`, {
      steps,
      extra_slots: [{ doc_id: APPLICATION, slot_id: "academic_supervisor" }],
      deadline: null,
      message: null,
    }),
    200,
  );
  expect(order(route)).toEqual([["author"], ["supervisor"], ["academic_supervisor"]]);
  for (const doc of route.docs)
    for (const slot of doc.slots)
      await client.json(
        await client.patch(
          `/api/v1/projects/${projectId}/signatures/placements/${doc.doc_id}/${slot.slot_id}`,
          { enabled: true, page: 1 },
        ),
        200,
      );
  await uploadPng(client, `/api/v1/projects/${projectId}/signatures/slots/author/png`);
  const preview = await client.json<Preview>(
    await client.post(`/api/v1/projects/${projectId}/signing-routes/${route.id}/preview`, {}),
    200,
  );
  expect(preview.blockers, JSON.stringify(preview.blockers)).toEqual([]);
  expect(preview.can_send).toBe(true);
  const sent = await client.json<Route>(
    await client.post(`/api/v1/projects/${projectId}/signing-routes/${route.id}/send`, {
      expected: Object.fromEntries(preview.docs.map((d) => [d.doc_id, d.token ?? ""])),
      sign: null,
    }),
    200,
  );
  expect(sent.status).toBe("active");
  expect(sent.current_step).toBe(2);
  return route.id;
};

/** «Отправить новую версию» на карточке: подтверждение со следствиями и полем «Что изменилось» (12.6). */
export const newVersionFromCard = async (page: Page, route: Route, note: string): Promise<void> => {
  const left = Date.parse(route.sent_at ?? "") + RESEND_INTERVAL_MS - Date.now();
  if (left > 0) {
    log(`до новой версии ${Math.ceil(left / 1000)} с`);
    await page.waitForTimeout(left);
  }
  await page.getByTestId("signing-new-version").click();
  await expect(page.getByTestId("signing-new-version-summary")).toBeVisible();
  await page.getByTestId("signing-new-version-note").fill(note);
  const reply = page.waitForResponse(
    (r) => r.request().method() === "POST" && r.url().endsWith(`/signing-routes/${route.id}/send`),
  );
  await page.getByTestId("signing-new-version-confirm").click();
  const res = await reply;
  expect(res.status(), await res.text()).toBe(200);
};

// ---------------------------------------------------------------- страница подписанта

export const checkpointPath = (projectId: string): string =>
  `/projects/${projectId}/submit/cp/${PROFILE}`;

export const signingPath = (projectId: string, routeId: string): string =>
  `/sign/${projectId}/${routeId}`;

/** «Входящие → На подпись»: задача маршрута, «Открыть» ведёт на страницу подписи. */
export const openFromInbox = async (page: Page, projectId: string, routeId: string) => {
  await page.goto("/inbox?tab=signing");
  const task = page.getByTestId(`inbox-signing-task-${routeId}`);
  await expect(task).toBeVisible();
  await page.getByTestId(`inbox-signing-open-${routeId}`).click();
  await expect(page).toHaveURL(new RegExp(`${signingPath(projectId, routeId)}$`));
  await expect(page.getByTestId("signing-page")).toHaveAttribute("data-state", "turn");
};

/** Подпись пальцем или мышью на листе страницы подписанта. */
export const drawSignature = async (page: Page): Promise<void> => {
  await page.getByTestId("signing-image-draw").click();
  const canvas = page.getByTestId("signing-draw-canvas");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("лист подписи без размеров");
  await page.mouse.move(box.x + box.width * 0.15, box.y + box.height * 0.6);
  await page.mouse.down();
  for (let i = 1; i <= 24; i += 1)
    await page.mouse.move(
      box.x + box.width * (0.15 + i * 0.03),
      box.y + box.height * (0.6 - 0.25 * Math.sin(i / 3)),
    );
  await page.mouse.up();
  await page.getByTestId("signing-draw-done").click();
  await expect(page.getByTestId("signing-image-ready")).toBeVisible();
};

export const approveOnPage = async (page: Page): Promise<void> => {
  const primary = page.getByTestId("signing-primary");
  await expect(primary).toHaveAttribute("data-label", "approve");
  await expect(primary).toHaveAttribute("data-blocked", "");
  await primary.click();
  await expect(page.getByTestId("signing-page")).not.toHaveAttribute("data-state", "turn");
};

export const signingTasks = async (client: Client): Promise<string[]> =>
  (
    await client.json<{ items: { route_id: string }[] }>(
      await client.get("/api/v1/account/signing-tasks"),
      200,
    )
  ).items.map((t) => t.route_id);

/** Сборка кнопкой документа: ждём ответ на запуск и итог сборки. */
export const buildInUi = async (
  page: Page,
  client: Client,
  projectId: string,
  docId: string,
): Promise<void> => {
  const started = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      r.url().endsWith(`/projects/${projectId}/documents/${docId}/compile`),
  );
  await page.getByTestId("document-build-button").click();
  // Документ идущего маршрута: мягкое предупреждение спрашивает один раз за сеанс (12.7).
  const proceed = page.getByRole("dialog").getByRole("button", { name: "Продолжить" });
  if (await proceed.waitFor({ state: "visible", timeout: 3_000 }).then(() => true, () => false)) {
    await proceed.click();
  }
  const res = await started;
  expect(res.status(), await res.text()).toBe(202);
  const { compile_id } = (await res.json()) as { compile_id: string };
  await waitCompiled(client, projectId, docId, compile_id);
};

/** Сколько картинок (XObject /Image) в PDF: штампы-картинки добавляют свои. */
/** ASCII85 (фильтр /ASCII85Decode, им ReportLab кодирует потоки поддельной сборки) в байты. */
const ascii85 = (text: string): Buffer => {
  const clean = text.replace(/\s+/g, "").replace(/^<~/, "").replace(/~>$/, "");
  const out: number[] = [];
  let group: number[] = [];
  const flush = (count: number): void => {
    let value = 0;
    for (const digit of group) value = value * 85 + digit;
    const bytes = [value >>> 24, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff];
    out.push(...bytes.slice(0, count));
  };
  for (const ch of clean) {
    if (ch === "z" && group.length === 0) {
      out.push(0, 0, 0, 0);
      continue;
    }
    group.push(ch.charCodeAt(0) - 33);
    if (group.length === 5) {
      flush(4);
      group = [];
    }
  }
  if (group.length > 0) {
    const count = group.length - 1;
    while (group.length < 5) group.push(84);
    flush(count);
  }
  return Buffer.from(out);
};

/**
 * Отпечаток исходников, из которых поддельный TeX собрал PDF (строка «sources sha256 …» на странице,
 * fake_tex_runner.py). Переживает штампы картинок и плашек: по нему видно, какая сборка лежит в PDF, даже если
 * байты файла другие. Потоки бывают ASCII85+Flate (ReportLab), Flate (после штампа) и без сжатия.
 */
export const buildDigest = (pdf: Buffer): string | null => {
  const found = new Set<string>();
  const scan = (text: string): void => {
    for (const m of text.matchAll(/sources sha256 ([0-9a-f]{64})/g)) found.add(m[1]!);
  };
  const raw = pdf.toString("latin1");
  scan(raw);
  for (const m of raw.matchAll(/stream\r?\n([\s\S]*?)endstream/g)) {
    const data = Buffer.from(m[1]!, "latin1");
    for (const decode of [
      () => inflateSync(ascii85(m[1]!)),
      () => inflateSync(data),
    ]) {
      try {
        scan(decode().toString("latin1"));
        break;
      } catch {
        // не тот фильтр: пробуем следующий
      }
    }
  }
  if (found.size > 1) throw new Error(`в PDF несколько сборок: ${[...found].join(", ")}`);
  return found.size === 1 ? [...found][0]! : null;
};

export const imageCount = (pdf: Buffer): number =>
  (pdf.toString("latin1").match(/\/Subtype\s*\/Image/g) ?? []).length;

// ---------------------------------------------------------------- текст страницы PDF

/** Байты потока PDF: без сжатия, Flate или ASCII85+Flate (ReportLab поддельной сборки). */
const streamBytes = (body: string): Buffer => {
  const data = Buffer.from(body, "latin1");
  for (const decode of [() => inflateSync(ascii85(body)), () => inflateSync(data)]) {
    try {
      return decode();
    } catch {
      // не тот фильтр: пробуем следующий
    }
  }
  return data;
};

/** Литеральная строка PDF `( … )` без скобок в байты: экранирование `\n`, `\(`, `\ddd`. */
const literalBytes = (inner: string): number[] => {
  const out: number[] = [];
  for (let i = 0; i < inner.length; i += 1) {
    const ch = inner[i]!;
    if (ch !== "\\") {
      out.push(ch.charCodeAt(0) & 0xff);
      continue;
    }
    const next = inner[i + 1] ?? "";
    const octal = /^[0-7]{1,3}/.exec(inner.slice(i + 1, i + 4));
    if (octal) {
      out.push(parseInt(octal[0], 8) & 0xff);
      i += octal[0].length;
      continue;
    }
    const escaped: Record<string, number> = { n: 10, r: 13, t: 9, b: 8, f: 12 };
    i += 1;
    if (next === "\r" || next === "\n") continue;
    out.push(escaped[next] ?? next.charCodeAt(0));
  }
  return out;
};

/** ToUnicode шрифта: однобайтовый код в текст (`bfchar` и `bfrange`, как пишут ReportLab и TeX). */
const toUnicode = (cmap: string): Map<number, string> => {
  const map = new Map<number, string>();
  const hexText = (hex: string): string => {
    let text = "";
    for (let i = 0; i + 4 <= hex.length; i += 4) text += String.fromCharCode(parseInt(hex.slice(i, i + 4), 16));
    return text;
  };
  for (const block of cmap.matchAll(/beginbfchar([\s\S]*?)endbfchar/g))
    for (const m of block[1]!.matchAll(/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>/g))
      map.set(parseInt(m[1]!, 16), hexText(m[2]!));
  for (const block of cmap.matchAll(/beginbfrange([\s\S]*?)endbfrange/g))
    for (const m of block[1]!.matchAll(/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>/g)) {
      const start = parseInt(m[3]!, 16);
      for (let code = parseInt(m[1]!, 16); code <= parseInt(m[2]!, 16); code += 1)
        map.set(code, String.fromCharCode(start + code - parseInt(m[1]!, 16)));
    }
  return map;
};

/**
 * Текстовые строки страниц PDF: по строке на каждый показ текста (`Tj`, `TJ`), в порядке потоков. Хватает для
 * PDF поддельной сборки и штампов Студии: объекты без потоков объектов, шрифты простые (однобайтовые коды).
 * Код переводится в текст по ToUnicode выбранного шрифта (`/Имя кегль Tf`); у шрифта без ToUnicode (Helvetica
 * поддельной сборки) байт и есть буква. Так читаются и метки даты: DejaVu Sans ReportLab кладёт кириллицу
 * кодами 1, 2, 3… своего подмножества.
 */
export const pdfTexts = (pdf: Buffer): string[] => {
  const raw = pdf.toString("latin1");
  const objects = new Map<number, string>();
  for (const m of raw.matchAll(/(\d+)\s+0\s+obj\b([\s\S]*?)endobj/g)) objects.set(Number(m[1]), m[2]!);
  const streamOf = (body: string): string | null => {
    const m = /stream\r?\n([\s\S]*?)\r?\nendstream/.exec(body);
    return m ? streamBytes(m[1]!).toString("latin1") : null;
  };
  // Шрифты с ToUnicode по номеру объекта, затем имя ресурса (`/F2+0 9 0 R`) в его карту.
  const cmaps = new Map<number, Map<number, string>>();
  for (const [num, body] of objects) {
    const ref = /\/ToUnicode\s+(\d+)\s+0\s+R/.exec(body);
    if (!ref || !/\/Type\s*\/Font\b/.test(body)) continue;
    const cmap = streamOf(objects.get(Number(ref[1])) ?? "");
    if (cmap) cmaps.set(num, toUnicode(cmap));
  }
  const fonts = new Map<string, Map<number, string>>();
  for (const body of objects.values())
    for (const m of body.matchAll(/\/([^\s/<>[\]()]+)\s+(\d+)\s+0\s+R/g)) {
      const cmap = cmaps.get(Number(m[2]));
      if (cmap) fonts.set(m[1]!, cmap);
    }
  const decode = (bytes: number[], font: string | null): string => {
    const cmap = font === null ? undefined : fonts.get(font);
    return bytes.map((b) => cmap?.get(b) ?? String.fromCharCode(b)).join("");
  };
  const hexBytes = (hex: string): number[] => {
    const clean = hex.replace(/\s+/g, "");
    const out: number[] = [];
    for (let i = 0; i < clean.length; i += 2) out.push(parseInt(clean.slice(i, i + 2).padEnd(2, "0"), 16));
    return out;
  };
  const texts: string[] = [];
  const string = String.raw`\((?:\\[\s\S]|[^\\)])*\)|<[0-9A-Fa-f\s]*>`;
  const token = new RegExp(
    String.raw`\/([^\s/<>[\]()]+)\s+[-\d.]+\s+Tf|(${string})\s*Tj|\[((?:${string}|[^\]])*)\]\s*TJ`,
    "g",
  );
  const piece = new RegExp(string, "g");
  const bytesOf = (s: string): number[] => (s.startsWith("(") ? literalBytes(s.slice(1, -1)) : hexBytes(s.slice(1, -1)));
  for (const body of objects.values()) {
    if (!/stream\r?\n/.test(body) || /\/(Length1|Subtype\s*\/Image|Type\s*\/XObject)\b/.test(body)) continue;
    const content = streamOf(body);
    if (content === null || !/\bBT\b/.test(content)) continue;
    let font: string | null = null;
    for (const m of content.matchAll(token)) {
      if (m[1] !== undefined) font = m[1];
      else if (m[2] !== undefined) texts.push(decode(bytesOf(m[2]), font));
      else if (m[3] !== undefined)
        texts.push([...m[3].matchAll(piece)].map((p) => decode(bytesOf(p[0]), font)).join(""));
    }
  }
  return texts;
};
