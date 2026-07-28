import { describe, expect, it } from "vitest";

import type { HsePersonDetail } from "../api";
import { toPersonFields } from "./toPersonFields";

const detail = (over: Partial<HsePersonDetail>): HsePersonDetail => ({
  id: "1",
  full_name: "Абанкина Ирина Всеволодовна",
  position: "Профессор",
  department: "Департамент образовательных программ",
  degree: "Кандидат экономических наук",
  profile_url: "https://www.hse.ru/org/persons/1",
  photo_url: "https://www.hse.ru/org/persons/cimage/1",
  ...over,
});

describe("toPersonFields", () => {
  it("combines position and department into the должность line", () => {
    expect(toPersonFields(detail({}))).toEqual({
      name: "Абанкина Ирина Всеволодовна",
      title: "Профессор, Департамент образовательных программ",
      degree: "Кандидат экономических наук",
    });
  });

  it("omits an empty department from the title", () => {
    expect(toPersonFields(detail({ department: "" })).title).toBe("Профессор");
  });

  it("yields an empty title when neither position nor department is known", () => {
    expect(toPersonFields(detail({ position: "", department: "" })).title).toBe(
      "",
    );
  });
});
