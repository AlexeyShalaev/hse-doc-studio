import { describe, expect, it } from "vitest";
import { ProjectResponseSchema } from "./projectSchemas";

// Детали проекта (GET /projects/{id}) одной формы в обоих режимах: на сервере
// приходят владелец и роль смотрящего, в локальном режиме эти поля null.
const DETAIL = {
  id: "8f1c2a4e-0000-4000-8000-000000000001",
  name: "Курсовая",
  folder: "",
  lock: {
    pack_id: "hse-cs-sse",
    template_id: "coursework",
    version: "2026.1",
    engine: "xelatex",
  },
  kind: "project",
  staffing: "solo",
  lang: "ru",
  authors: [],
  supervisor: null,
  co_supervisor: null,
  academic_supervisor: null,
  meta: {},
  created_at: "2026-10-30T10:00:00Z",
  updated_at: "2026-10-30T10:00:00Z",
  shared_enabled: true,
  pinned: false,
  archived: false,
  checks_override: {
    disabled_categories: [],
    disabled: [],
    enabled: [],
    severity_override: {},
  },
  access: { mode: "full", reasons: [], required_studio: null },
  storage: null,
};

describe("ProjectResponseSchema: детали проекта", () => {
  it("на сервере несут владельца и роль смотрящего", () => {
    const parsed = ProjectResponseSchema.parse({
      ...DETAIL,
      owner: {
        kind: "user",
        id: "850212210875490d8c937914daed88cd",
        name: "Анна",
        slug: null,
      },
      my_role: "owner",
    });
    expect(parsed.my_role).toBe("owner");
    expect(parsed.owner?.kind).toBe("user");
  });

  it("в локальном режиме владельца и роли нет: null принимается", () => {
    const parsed = ProjectResponseSchema.parse({
      ...DETAIL,
      owner: null,
      my_role: null,
    });
    expect(parsed.my_role ?? null).toBeNull();
  });
});
