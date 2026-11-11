import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  MAIL_FAILURES,
  MAIL_LOG_CONTRACT_SCHEMAS,
  MAIL_SKIP_REASONS,
  MAIL_STATUSES,
  MAIL_TEMPLATE_GROUPS,
  MAIL_TEMPLATES,
  MailLogDetailSchema,
  MailLogEntrySchema,
  MailLogPageSchema,
  MailLogSummarySchema,
} from "./schemas";
import {
  MAIL_JOURNALS,
  MAIL_LOG_CONTRACT_EXAMPLES,
  MAIL_LOG_DETAILS,
  MAIL_LOG_PAGES,
  MAIL_LOG_SUMMARIES,
  makeMailLogDetail,
} from "../testing/fixtures";
import {
  mailHintOf,
  mailFailureOf,
  mailTemplateGroup,
  parseMailId,
  skippedCount,
} from "../lib/mailLog";

// Журнал писем (mail-log.md, 6.2): эталоны, состояния галереи и сверка видов писем с сервером.

const REPO = join(import.meta.dirname, "..", "..", "..", "..", "..", "..");
const LOCALES = join(
  REPO,
  "services",
  "web-app",
  "src",
  "shared",
  "lib",
  "i18n",
  "locales",
);

const examples = Object.entries(MAIL_LOG_CONTRACT_EXAMPLES).flatMap(
  ([schema, variants]) =>
    Object.entries(variants).map(
      ([name, body]) => [`${schema}/${name}`, schema, body] as const,
    ),
);

describe("журнал писем: эталоны контракта", () => {
  it("у каждой схемы есть эталон, у каждого эталона схема", () => {
    expect(Object.keys(MAIL_LOG_CONTRACT_EXAMPLES).sort()).toEqual(
      Object.keys(MAIL_LOG_CONTRACT_SCHEMAS).sort(),
    );
  });

  it.each(examples)("%s разбирается zod без потерь", (_l, schema, body) => {
    const parsed = MAIL_LOG_CONTRACT_SCHEMAS[schema]?.safeParse(body);
    expect(parsed?.success).toBe(true);
    expect(parsed?.data).toEqual(body);
  });

  it.each(examples)("%s: лишнее поле отвергается", (_l, schema, body) => {
    const extra = { ...(body as Record<string, unknown>), surprise: 1 };
    expect(MAIL_LOG_CONTRACT_SCHEMAS[schema]?.safeParse(extra).success).toBe(
      false,
    );
  });

  it("поле нельзя опустить: пустое значение приходит null", () => {
    const { project: _project, ...rest } = MAIL_LOG_DETAILS.token_link.entry;
    expect(MailLogEntrySchema.safeParse(rest).success).toBe(false);
  });

  it("неизвестный итог и вызвавший отвергаются, неизвестный вид письма нет", () => {
    const entry = MAIL_LOG_DETAILS.token_link.entry;
    expect(
      MailLogEntrySchema.safeParse({ ...entry, status: "sending" }).success,
    ).toBe(false);
    expect(
      MailLogEntrySchema.safeParse({ ...entry, cause: "robot" }).success,
    ).toBe(false);
    expect(
      MailLogEntrySchema.safeParse({
        ...entry,
        template: "weekly_digest",
        template_known: false,
      }).success,
    ).toBe(true);
  });
});

describe("журнал писем: состояния галереи", () => {
  it("страницы, карточки и сводки проходят схемы", () => {
    for (const page of Object.values(MAIL_LOG_PAGES)) {
      expect(MailLogPageSchema.parse(page)).toEqual(page);
    }
    for (const detail of Object.values(MAIL_LOG_DETAILS)) {
      expect(MailLogDetailSchema.parse(detail)).toEqual(detail);
    }
    for (const summary of Object.values(MAIL_LOG_SUMMARIES)) {
      expect(MailLogSummarySchema.parse(summary)).toEqual(summary);
    }
  });

  it("обычный журнал покрывает все виды, итоги, классы сбоев и причины пропуска", () => {
    const entries = MAIL_JOURNALS.default.map((r) => r.entry);
    const templates = new Set(entries.map((e) => e.template));
    expect(MAIL_TEMPLATES.filter((t) => !templates.has(t))).toEqual([]);
    expect(entries.some((e) => !e.template_known)).toBe(true);
    expect(new Set(entries.map((e) => e.status))).toEqual(
      new Set(MAIL_STATUSES),
    );
    const failures = new Set(
      entries.filter((e) => e.status === "failed").map((e) => e.reason),
    );
    expect(
      MAIL_FAILURES.filter((f) => f !== "smtp_off" && !failures.has(f)),
    ).toEqual([]);
    const skipped = new Set(
      entries.filter((e) => e.status !== "sent").map((e) => e.reason),
    );
    expect(MAIL_SKIP_REASONS.filter((r) => !skipped.has(r))).toEqual([]);
    expect(new Set(entries.map((e) => e.cause))).toEqual(
      new Set(["user", "anonymous", "system"]),
    );
  });

  it("журнал идёт от новых к старым, id убывают", () => {
    for (const journal of Object.values(MAIL_JOURNALS)) {
      const ids = journal.map((r) => r.entry.id);
      expect(ids).toEqual([...ids].sort((a, b) => b - a));
      const times = journal.map((r) => Date.parse(r.entry.at));
      expect(times).toEqual([...times].sort((a, b) => b - a));
    }
  });

  it("только у sent есть Message-ID, только у failed ответ SMTP", () => {
    for (const { entry } of MAIL_JOURNALS.default) {
      expect(entry.message_id !== null).toBe(entry.status === "sent");
      expect(entry.failure !== null).toBe(entry.status === "failed");
      expect(entry.actor !== null).toBe(entry.cause === "user");
      expect(entry.task !== null).toBe(entry.cause === "system");
    }
  });

  it("сводка считает итоги только за сутки", () => {
    const day = MAIL_LOG_SUMMARIES.day;
    expect(day.window_hours).toBe(24);
    expect(day.sent + day.failed + day.not_sent + day.suppressed).toBe(13);
    expect(day.failed).toBe(2);
    expect(day.not_sent).toBe(0);
    expect(day.last_failure?.reason).toBe("recipient_refused");
    expect(MAIL_LOG_SUMMARIES.smtp_off).toMatchObject({
      smtp_configured: false,
      sent: 0,
      failed: 0,
    });
    expect(MAIL_LOG_SUMMARIES.smtp_off.not_sent).toBeGreaterThan(0);
    expect(MAIL_LOG_SUMMARIES.auth_failure.last_failure?.reason).toBe("auth");
    expect(MAIL_LOG_SUMMARIES.quiet.last_failure).toBeNull();
  });
});

describe("журнал писем: превью без ссылок и сообщений", () => {
  it("ссылка с токеном скрыта: кнопка без href, в тексте «[ссылка скрыта]»", () => {
    const detail = MAIL_LOG_DETAILS.token_link;
    expect(detail.link_hidden).toBe(true);
    expect(detail.preview?.html).not.toMatch(/href=/);
    expect(detail.preview?.html).toContain("[ссылка скрыта]");
    expect(detail.preview?.text).toContain("[ссылка скрыта]");
  });

  it("у письма без токена путь страницы текстом", () => {
    const detail = MAIL_LOG_DETAILS.signing_page;
    expect(detail.link_hidden).toBe(false);
    expect(detail.preview?.text).toContain(
      "https://studio.example.org/sign/p_01hxa1c4de/sr_01hy2b7k9q",
    );
    expect(detail.preview?.html).not.toMatch(/href=/);
  });

  it("сообщение человека заменено пометкой", () => {
    const detail = MAIL_LOG_DETAILS.invitation_note;
    expect(detail.note_hidden).toBe(true);
    expect(detail.preview?.text).toContain("[сообщение не хранится в журнале]");
  });

  it("английское письмо получает английские пометки", () => {
    const record = MAIL_JOURNALS.default.find(
      (r) => r.entry.lang === "en" && r.link === "page",
    );
    if (!record) throw new Error("нет английского письма со страницей");
    const detail = makeMailLogDetail({ ...record, link: "token", note_len: 5 });
    expect(detail.preview?.text).toContain("[link hidden]");
    expect(detail.preview?.text).toContain("[message not kept in the log]");
  });

  it("перерисовка по новому шаблону: тема превью своя, тема строки как ушла", () => {
    const detail = MAIL_LOG_DETAILS.rerendered;
    expect(detail.rerendered).toBe(true);
    expect(detail.preview?.subject).not.toBe(detail.entry.subject);
  });

  it("вида письма нет: превью нет", () => {
    const detail = MAIL_LOG_DETAILS.template_gone;
    expect(detail.entry.template_known).toBe(false);
    expect(detail.preview).toBeNull();
    expect(detail.rerendered).toBe(false);
  });

  it("имена и темы экранируются", () => {
    const record = MAIL_JOURNALS.default[1];
    if (!record) throw new Error("пустой журнал");
    const detail = makeMailLogDetail({
      ...record,
      entry: { ...record.entry, subject: "<script>alert(1)</script>" },
    });
    expect(detail.preview?.html).not.toContain("<script>");
  });
});

describe("журнал писем: виды писем совпадают с сервером и подписями", () => {
  it("MAIL_TEMPLATES это MailTemplate из core/mail/compose.py", () => {
    const source = readFileSync(
      join(
        REPO,
        "services",
        "api",
        "hse_doc_studio",
        "core",
        "mail",
        "compose.py",
      ),
      "utf8",
    );
    const block = /class MailTemplate\(StrEnum\):([\s\S]*?)\n\n\n/.exec(
      source,
    )?.[1];
    const values = [...(block ?? "").matchAll(/=\s*"([a-z_]+)"/g)].map(
      (m) => m[1],
    );
    expect(values).toEqual([...MAIL_TEMPLATES]);
  });

  it("группы фильтра делят все виды без пересечений", () => {
    const grouped = Object.values(MAIL_TEMPLATE_GROUPS).flat();
    expect([...grouped].sort()).toEqual([...MAIL_TEMPLATES].sort());
    expect(mailTemplateGroup("signing_reminder")).toBe("signing");
    expect(mailTemplateGroup("weekly_digest")).toBeNull();
  });

  it.each(["ru", "en"])(
    "у каждого вида есть подпись adminSettings:mailPreview.names (%s)",
    (lng) => {
      const settings = JSON.parse(
        readFileSync(join(LOCALES, lng, "admin", "settings.json"), "utf8"),
      ) as { mailPreview: { names: Record<string, string> } };
      expect(
        MAIL_TEMPLATES.filter((t) => !settings.mailPreview.names[t]?.trim()),
      ).toEqual([]);
    },
  );
});

describe("журнал писем: правила экрана", () => {
  it("подсказка под полосой по последнему сбою", () => {
    expect(mailHintOf(MAIL_LOG_SUMMARIES.auth_failure)).toBe("auth");
    expect(mailHintOf(MAIL_LOG_SUMMARIES.day)).toBeNull();
    const at = "2026-11-11T09:00:00Z";
    const base = MAIL_LOG_SUMMARIES.day;
    expect(
      mailHintOf({ ...base, last_failure: { at, reason: "timeout" } }),
    ).toBe("connect");
    expect(mailHintOf({ ...base, last_failure: { at, reason: "tls" } })).toBe(
      "tls",
    );
  });

  it("«Не отправлялось» складывает not_sent и suppressed", () => {
    const s = MAIL_LOG_SUMMARIES.smtp_off;
    expect(skippedCount(s)).toBe(s.not_sent + s.suppressed);
  });

  it("неизвестный класс сбоя показывается как other", () => {
    expect(mailFailureOf("recipient_refused")).toBe("recipient_refused");
    expect(mailFailureOf("quantum")).toBe("other");
    expect(mailFailureOf(null)).toBe("other");
  });

  it("номер письма из адреса", () => {
    expect(parseMailId("42")).toBe(42);
    expect(parseMailId(null)).toBeNull();
    expect(parseMailId("0")).toBeNull();
    expect(parseMailId("4x")).toBeNull();
    expect(parseMailId("-3")).toBeNull();
  });
});
