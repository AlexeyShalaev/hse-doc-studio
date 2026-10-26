import { describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import { failedProbe, makeProbe } from "../testing/connectFixtures";
import {
  accessOf,
  cloneVerdictFromError,
  cloneVerdictFromProbe,
} from "./cloneVerdict";

describe("accessOf", () => {
  it("полный доступ, когда схема и шаблон подходят", () => {
    expect(accessOf("full", true)).toEqual({ access: "full", reasons: [] });
    expect(accessOf(null, null)).toEqual({ access: "full", reasons: [] });
  });

  it("новая схема даёт чтение или только файлы с причиной", () => {
    expect(accessOf("read_only", true)).toEqual({
      access: "read_only",
      reasons: ["schema_newer"],
    });
    expect(accessOf("files_only", null)).toEqual({
      access: "files_only",
      reasons: ["schema_newer"],
    });
  });

  it("нет шаблона: только чтение, причина названа", () => {
    expect(accessOf("full", false)).toEqual({
      access: "read_only",
      reasons: ["template_missing"],
    });
  });

  it("новая схема и нет шаблона: остаётся более строгий доступ, причины обе", () => {
    expect(accessOf("files_only", false)).toEqual({
      access: "files_only",
      reasons: ["schema_newer", "template_missing"],
    });
  });

  it("неизвестное значение схемы не ломает вывод", () => {
    expect(accessOf("from_the_future", true)).toEqual({
      access: "full",
      reasons: [],
    });
  });
});

describe("cloneVerdictFromProbe", () => {
  it("проект Студии можно клонировать", () => {
    expect(
      cloneVerdictFromProbe(makeProbe({ relation: "studio_project" })),
    ).toEqual({
      kind: "ready",
      access: "full",
      reasons: [],
      requiredStudio: null,
    });
  });

  it("связь «тот же проект» тоже значит проект Студии", () => {
    expect(
      cloneVerdictFromProbe(makeProbe({ relation: "same_project" })).kind,
    ).toBe("ready");
  });

  it("называет нужную версию Студии", () => {
    expect(
      cloneVerdictFromProbe(
        makeProbe({
          schema_access: "read_only",
          required_studio: "0.4.0",
        }),
      ),
    ).toEqual({
      kind: "ready",
      access: "read_only",
      reasons: ["schema_newer"],
      requiredStudio: "0.4.0",
    });
  });

  it("пустой репозиторий и чужие данные останавливают", () => {
    expect(
      cloneVerdictFromProbe(makeProbe({ relation: "empty", empty: true })),
    ).toEqual({ kind: "empty" });
    expect(
      cloneVerdictFromProbe(makeProbe({ relation: "not_studio_project" })),
    ).toEqual({ kind: "not_studio" });
  });

  it("отказ сервера становится ошибкой с кодом и ключами хоста", () => {
    const verdict = cloneVerdictFromProbe(
      failedProbe("host_key_unknown", "", {}, [
        { type: "ssh-ed25519", fingerprint_sha256: "SHA256:abc" },
      ]),
    );
    expect(verdict.kind).toBe("error");
    if (verdict.kind !== "error") return;
    expect(verdict.issue.code).toBe("host_key_unknown");
    expect(verdict.issue.hostKeys).toHaveLength(1);
  });

  it("неясная связь без проекта: общая ошибка, а не обещание клонировать", () => {
    const verdict = cloneVerdictFromProbe(
      makeProbe({ relation: "unknown", project: null }),
    );
    expect(verdict.kind).toBe("error");
  });
});

describe("cloneVerdictFromError", () => {
  it("берёт код из ответа сервера", () => {
    const verdict = cloneVerdictFromError(
      new ApiError("Не тот адрес", "url_scheme_forbidden", 400),
    );
    expect(verdict.kind).toBe("error");
    if (verdict.kind !== "error") return;
    expect(verdict.issue.code).toBe("url_scheme_forbidden");
  });

  it("not_a_studio_project это не ошибка, а исход «не проект Студии»", () => {
    expect(
      cloneVerdictFromError(
        new ApiError("Нет проекта", "not_a_studio_project", 409),
      ),
    ).toEqual({ kind: "not_studio" });
  });

  it("сетевая ошибка без кода остаётся общей ошибкой", () => {
    const verdict = cloneVerdictFromError(new Error("Network Error"));
    expect(verdict.kind).toBe("error");
  });
});
