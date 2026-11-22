import { describe, expect, it } from "vitest";
import type { PackOutcome } from "@entities/pack-studio";
import {
  COURSEWORK_OUTCOME,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import {
  studentDocuments,
  studentForms,
  studentMeta,
  studentRoute,
} from "./studentView";

// Вид «Как студент»: те же данные ответа сервера без служебного. Условий здесь нет, проверяется
// только, что берутся готовые флаги ответа и ничего служебного не просачивается.

const vkr = (edit?: (o: PackOutcome) => void): PackOutcome => {
  const out = structuredClone(VKR_OUTCOME);
  edit?.(out);
  return out;
};

describe("studentDocuments", () => {
  it("только документы в комплекте, с итоговыми именами файлов", () => {
    const docs = studentDocuments(vkr(), "ru");
    const ids = docs.map((d) => d.id);
    expect(ids).toContain("technical_specification");
    // Выключенный (inactive) и отсутствующий (absent) студент не получит.
    expect(ids).not.toContain("operator_manual");
    expect(ids).not.toContain("annotation");
    const spec = docs.find((d) => d.id === "technical_specification");
    expect(spec?.name).toBe("Техническое задание");
    expect(spec?.files).toEqual([
      { owner: null, name: "Техническое задание.pdf" },
    ]);
    expect(spec?.required).toBe(true);
  });

  it("название берётся на языке интерфейса", () => {
    const docs = studentDocuments(vkr(), "en");
    expect(docs.find((d) => d.id === "technical_specification")?.name).toBe(
      "Statement of Work",
    );
  });

  it("документ без имени файла не даёт пустой строки файла", () => {
    const out = vkr((o) => {
      const doc = o.documents.find((d) => d.id === "thesis");
      if (doc) for (const inst of doc.instances) inst.file_name = null;
    });
    expect(
      studentDocuments(out, "ru").find((d) => d.id === "thesis")?.files,
    ).toEqual([]);
  });
});

describe("studentMeta и studentForms", () => {
  it("поля по моменту обязательности, необязательные и скрытые не показываются", () => {
    const meta = studentMeta(vkr(), "ru");
    expect(meta.create.map((f) => f.id)).toEqual([
      "year",
      "specialization",
      "supervisor",
    ]);
    expect(meta.finalize.map((f) => f.id)).toEqual(["udc", "doc_code_base"]);
    const hidden = vkr((o) => {
      const year = o.meta.find((m) => m.id === "year");
      if (year) year.visible = false;
    });
    expect(studentMeta(hidden, "ru").create.map((f) => f.id)).not.toContain(
      "year",
    );
  });

  it("поле автора помечено, что его заполняет каждый автор", () => {
    const meta = studentMeta(vkr(), "ru");
    expect(meta.finalize.every((f) => f.perAuthor)).toBe(true);
    expect(meta.create.some((f) => f.perAuthor)).toBe(false);
  });

  it("анкеты: только применяемые, только видимые поля", () => {
    const forms = studentForms(vkr(), "ru");
    const ai = forms.find((f) => f.id === "ai_declaration");
    expect(ai?.title).toBe("Декларация об использовании ИИ");
    expect(ai?.fields.map((f) => f.id)).toEqual([
      "used_ai",
      "clauses",
      "consent",
    ]);
    const off = vkr((o) => {
      const form = o.forms.find((f) => f.id === "code_link");
      if (form) form.applies = false;
    });
    expect(studentForms(off, "ru").map((f) => f.id)).toEqual([
      "ai_declaration",
    ]);
  });
});

describe("studentRoute", () => {
  it("точки с шагами по порядку, каждому подписанту его документы", () => {
    const points = studentRoute(vkr(), "ru");
    expect(points.map((p) => p.id)).toEqual([
      "pdp-application",
      "final",
      "gia",
    ]);
    const pdp = points[0];
    expect(pdp?.steps.map((s) => s.map((p) => p.persona))).toEqual([
      ["author"],
      ["supervisor"],
    ]);
    // Подписи автора в точке: два документа, названия, а не идентификаторы.
    const names = pdp?.steps[0]?.[0]?.documents.map((d) => d.name) ?? [];
    expect(names).toHaveLength(2);
    expect(names.some((n) => n.includes("_"))).toBe(false);
  });

  it("участник, которого нет в комбинации, и пустой шаг пропускаются", () => {
    const out = vkr((o) => {
      for (const p of o.participants) {
        if (p.persona === "supervisor") {
          p.present = false;
          p.name = "";
        }
      }
    });
    const pdp = studentRoute(out, "ru").find((p) => p.id === "pdp-application");
    expect(pdp?.steps).toHaveLength(1);
    expect(pdp?.steps[0]?.[0]?.persona).toBe("author");
  });

  it("срок и необязательная подпись из ответа", () => {
    const out = structuredClone(COURSEWORK_OUTCOME);
    const topic = out.points.find((p) => p.id === "topic-approval");
    const pair = topic?.route.pairs.find((p) => p.persona === "co_supervisor");
    if (pair) pair.optional = true;
    const point = studentRoute(out, "ru").find(
      (p) => p.id === "topic-approval",
    );
    expect(point?.deadline).toContain("середине ноября");
    expect(point?.steps[1]).toHaveLength(2);
    const co = point?.steps[1]?.find((p) => p.persona === "co_supervisor");
    expect(co?.documents.some((d) => d.optional)).toBe(true);
  });

  it("точка без подписей в вид не попадает", () => {
    const points = studentRoute(structuredClone(COURSEWORK_OUTCOME), "ru");
    expect(points.map((p) => p.id)).toEqual(["topic-approval", "final"]);
  });
});
