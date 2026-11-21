import { describe, expect, it } from "vitest";
import { VERSION_SECTIONS } from "@features/pack-forms/ui/VersionForm";
import { CONTENT_PARTS } from "../contract";
import { PART_COMPONENTS } from "../registry";
import { SECTION } from "./VersionPart";

// Карта паритета (pack-studio-ux.md, 7.4, принцип P11): каждый раздел формы версии прежнего
// интерфейса достижим в «Содержимом». Тест ломается, если раздел добавили в форму версии и не
// подключили к навигации, или убрали раздел из навигации.

describe("карта паритета: разделы формы версии в «Содержимом»", () => {
  it("каждый раздел формы версии открывается из какого-то раздела навигации", () => {
    const reachable = new Set(Object.values(SECTION));
    for (const section of VERSION_SECTIONS) {
      expect(reachable.has(section.id as never), section.id).toBe(true);
    }
  });

  it("каждый раздел навигации «Содержимого» существует: у него есть файл-расширение", () => {
    for (const part of CONTENT_PARTS) {
      expect(PART_COMPONENTS[part], part).not.toBeNull();
    }
  });

  it("разделы формы версии: поля, анкеты, документы, языки, сдача и подписи, проверки", () => {
    expect(VERSION_SECTIONS.map((section) => section.id).sort()).toEqual([
      "checks",
      "documents",
      "fields",
      "forms",
      "languages",
      "submission",
    ]);
  });
});
