import { describe, expect, it } from "vitest";
import {
  buildPackPresetYaml,
  type PackPresetInput,
  type PresetPlacement,
} from "./packPreset";

const TEXTS = {
  header: "Preset for hse-cs-sse, template coursework, version 2026.1.3.",
  hint: "Move into signatures.slots.",
  asInPack: "as in the template",
};

const PACK: PackPresetInput["pack"] = {
  packId: "hse-cs-sse",
  templateId: "coursework",
  version: "2026.1.3",
  slots: [
    {
      id: "author",
      applies_to: ["topic_application", "report"],
      per_author: true,
    },
    { id: "supervisor", applies_to: ["project_proposal", "topic_application"] },
  ],
  documents: [
    { id: "project_proposal", scope: "shared" },
    { id: "topic_application", scope: "shared" },
    { id: "report", scope: "author" },
  ],
  supportedStaffing: ["solo"],
};

const place = (
  x_mm: number,
  y_mm: number,
  width_mm: number,
  extra: Partial<PresetPlacement> = {},
): PresetPlacement => ({
  enabled: true,
  page: 1,
  x_mm,
  y_mm,
  width_mm,
  dates: [],
  ...extra,
});

const build = (over: Partial<PackPresetInput>) =>
  buildPackPresetYaml({
    placements: {},
    documents: [],
    pack: PACK,
    texts: TEXTS,
    ...over,
  });

describe("buildPackPresetYaml", () => {
  it("округляет до 1 мм и пишет метки даты в порядке справки", () => {
    const preset = build({
      documents: [{ id: "project_proposal" }, { id: "topic_application" }],
      placements: {
        project_proposal: {
          supervisor: place(80.4, 138.6, 39.7, {
            dates: [
              {
                page: 1,
                x_mm: 81.2,
                y_mm: 156.4,
                width_mm: 7.3,
                height_mm: 5.1,
                format: "day",
                align: "center",
              },
              {
                page: 1,
                x_mm: 90,
                y_mm: 156,
                width_mm: 24,
                height_mm: 5,
                format: "month_word",
                align: "left",
              },
            ],
          }),
        },
        topic_application: {
          supervisor: place(163, 168, 40),
          author: place(165.2, 199.8, 30),
        },
      },
    });
    expect(preset.warnings).toEqual([]);
    expect(preset.yaml).toBe(
      [
        "# Preset for hse-cs-sse, template coursework, version 2026.1.3.",
        "# Move into signatures.slots.",
        "signatures:",
        "  slots:",
        "    - id: author",
        "      placements:",
        "        topic_application: { page: 1, x_mm: 165, y_mm: 200, width_mm: 30 }",
        "    - id: supervisor",
        "      placements:",
        "        project_proposal: { page: 1, x_mm: 80, y_mm: 139, width_mm: 40 }",
        "        topic_application: { page: 1, x_mm: 163, y_mm: 168, width_mm: 40 }",
        "      default_dates:",
        "        project_proposal:",
        "          - { page: 1, x_mm: 81, y_mm: 156, width_mm: 7, height_mm: 5, format: day }",
        "          - { page: 1, x_mm: 90, y_mm: 156, width_mm: 24, height_mm: 5, format: month_word, align: left }",
        "",
      ].join("\n"),
    );
  });

  it("приводит экземпляры команды к id пака и берёт место первого автора", () => {
    const preset = build({
      documents: [
        { id: "report--ivanov", def_id: "report" },
        { id: "report--petrova", def_id: "report" },
      ],
      placements: {
        "report--ivanov": { "author--ivanov": place(150, 250, 30) },
        "report--petrova": { "author--petrova": place(120, 250, 30) },
      },
    });
    expect(preset.entries).toEqual([
      {
        slot: "author",
        doc: "report",
        place: { page: 1, x_mm: 150, y_mm: 250, width_mm: 30 },
        dates: [],
        asInPack: false,
      },
    ]);
    expect(preset.warnings).toEqual([
      {
        code: "duplicate",
        slot: "author",
        doc: "report",
        kept: "report--ivanov",
        skipped: ["report--petrova"],
      },
    ]);
    expect(preset.yaml).toContain("report: { page: 1, x_mm: 150");
    expect(preset.yaml).not.toContain("ivanov");
    expect(preset.yaml).not.toContain("petrova");
  });

  it("одинаковые места авторов не предупреждают", () => {
    const preset = build({
      documents: [
        { id: "report--ivanov", def_id: "report" },
        { id: "report--petrova", def_id: "report" },
      ],
      placements: {
        "report--ivanov": { "author--ivanov": place(150.2, 250, 30) },
        "report--petrova": { "author--petrova": place(149.8, 250, 30) },
      },
    });
    expect(preset.entries).toHaveLength(1);
    expect(preset.warnings).toEqual([]);
  });

  it("пропускает свои слоты, выключенные места и неприменимые слоты", () => {
    const preset = build({
      documents: [{ id: "project_proposal" }, { id: "report" }],
      placements: {
        project_proposal: {
          dean: place(100, 100, 40),
          author: place(100, 120, 40),
          supervisor: place(80, 139, 40, { enabled: false }),
        },
        report: { supervisor: place(80, 139, 40) },
      },
    });
    expect(preset.yaml).toBe("");
    expect(preset.entries).toEqual([]);
    expect(preset.warnings).toEqual([
      { code: "custom_slot", slot: "dean" },
      { code: "not_applicable", slot: "author", doc: "project_proposal" },
      { code: "not_applicable", slot: "supervisor", doc: "report" },
      { code: "disabled", count: 1 },
    ]);
  });

  it("выключенные места берёт по галочке", () => {
    const preset = build({
      documents: [{ id: "project_proposal" }],
      placements: {
        project_proposal: {
          supervisor: place(80, 139, 40, { enabled: false }),
        },
      },
      includeDisabled: true,
    });
    expect(preset.entries).toHaveLength(1);
    expect(preset.warnings).toEqual([]);
  });

  it("пропускает рамку за краем листа и битые метки даты", () => {
    const preset = build({
      documents: [{ id: "project_proposal" }, { id: "topic_application" }],
      placements: {
        project_proposal: {
          supervisor: place(180, 139, 40, {
            dates: [
              {
                page: 1,
                x_mm: 205,
                y_mm: 150,
                width_mm: 20,
                height_mm: 5,
                format: "day",
                align: "center",
              },
            ],
          }),
        },
        topic_application: {
          supervisor: place(160, 168, 40, {
            dates: [
              {
                page: 1,
                x_mm: 205,
                y_mm: 150,
                width_mm: 20,
                height_mm: 5,
                format: "day",
                align: "center",
              },
            ],
          }),
        },
      },
    });
    expect(preset.warnings).toEqual([
      {
        code: "invalid_place",
        slot: "supervisor",
        doc: "project_proposal",
        problem: "edge",
      },
      {
        code: "invalid_date",
        slot: "supervisor",
        doc: "topic_application",
        index: 1,
        problem: "edge",
      },
    ]);
    expect(preset.entries.map((e) => [e.doc, e.dates.length])).toEqual([
      ["topic_application", 0],
    ]);
  });

  it("рамку у края, которую округление вытолкнуло бы, сужает, а узкую расширяет до 10 мм", () => {
    const preset = build({
      documents: [{ id: "project_proposal" }, { id: "topic_application" }],
      placements: {
        project_proposal: { supervisor: place(170.6, 100, 39.4) },
        topic_application: { supervisor: place(50, 100, 6) },
      },
    });
    expect(preset.entries.map((e) => e.place)).toEqual([
      { page: 1, x_mm: 171, y_mm: 100, width_mm: 39 },
      { page: 1, x_mm: 50, y_mm: 100, width_mm: 10 },
    ]);
  });

  it("место как в шаблоне выводит как есть с пометкой", () => {
    const preset = build({
      documents: [{ id: "project_proposal" }],
      placements: {
        project_proposal: {
          supervisor: place(80.25, 139, 40, { origin: "pack" }),
        },
      },
    });
    expect(preset.yaml).toContain(
      "project_proposal: { page: 1, x_mm: 80.25, y_mm: 139, width_mm: 40 }  # as in the template",
    );
  });

  it("берёт только выбранный документ", () => {
    const preset = build({
      documents: [{ id: "project_proposal" }, { id: "topic_application" }],
      placements: {
        project_proposal: { supervisor: place(80, 139, 40) },
        topic_application: { supervisor: place(163, 168, 40) },
      },
      docIds: ["topic_application"],
    });
    expect(preset.entries.map((e) => e.doc)).toEqual(["topic_application"]);
  });

  it("место per_author на общем документе командного шаблона пропускает", () => {
    const preset = build({
      pack: { ...PACK, supportedStaffing: ["solo", "team"] },
      documents: [{ id: "topic_application" }],
      placements: {
        topic_application: { "author--ivanov": place(165, 200, 30) },
      },
    });
    expect(preset.yaml).toBe("");
    expect(preset.warnings).toEqual([
      { code: "per_author_shared", slot: "author", doc: "topic_application" },
    ]);
  });

  it("лишние метки даты сверх восьми отбрасывает", () => {
    const marks = Array.from({ length: 9 }, (_, i) => ({
      page: 1,
      x_mm: 10 + i * 10,
      y_mm: 150,
      width_mm: 8,
      height_mm: 5,
      format: "day",
      align: "center",
    }));
    const preset = build({
      documents: [{ id: "project_proposal" }],
      placements: {
        project_proposal: { supervisor: place(80, 139, 40, { dates: marks }) },
      },
    });
    expect(preset.entries[0]?.dates).toHaveLength(8);
    expect(preset.warnings).toEqual([
      {
        code: "too_many_dates",
        slot: "supervisor",
        doc: "project_proposal",
        dropped: 1,
      },
    ]);
  });

  it("пустое состояние даёт пустой YAML", () => {
    const preset = build({});
    expect(preset).toEqual({ yaml: "", entries: [], warnings: [] });
  });
});

describe("buildPackPresetYaml с якорями (15.17.12)", () => {
  const ANCHOR_TEXTS = {
    ...TEXTS,
    anchorsHeader: "Taken from the build of 13 Nov.",
    byBuild: "by the build",
    noAnchor: "no anchor",
  };
  const BUILD = {
    items: [
      {
        id: "supervisor",
        kind: "sign" as const,
        page: 1,
        x_mm: 169.5,
        y_mm: 186.8,
        width_mm: 25.5,
      },
      {
        id: "supervisor.day",
        kind: "date" as const,
        page: 1,
        x_mm: 120,
        y_mm: 200,
        width_mm: 8,
      },
    ],
  };

  it("место из шаблона на якоре выводится записью пака как есть, с метками пака", () => {
    const preset = build({
      texts: ANCHOR_TEXTS,
      documents: [{ id: "topic_application" }],
      anchors: { topic_application: BUILD },
      runtimeSlots: [
        {
          id: "supervisor",
          default_placements: {
            topic_application: {
              source: "anchor",
              anchor: "supervisor",
              align: "right",
              dx_mm: 0,
              dy_mm: -10,
              width_mm: 28,
              fallback: null,
            },
          },
          default_dates: {
            topic_application: [
              {
                source: "anchor",
                anchor: "supervisor.day",
                format: "day",
                align: "center",
                height_mm: 5,
                width_mm: null,
                dx_mm: 0,
                dy_mm: null,
                fallback: null,
              },
            ],
          },
        },
      ],
      placements: {
        topic_application: {
          supervisor: place(167, 176.8, 28, {
            origin: "pack",
            source: "anchor",
          }),
        },
      },
    });
    expect(preset.yaml).toBe(
      [
        "# Preset for hse-cs-sse, template coursework, version 2026.1.3.",
        "# Move into signatures.slots.",
        "# Taken from the build of 13 Nov.",
        "signatures:",
        "  slots:",
        "    - id: supervisor",
        "      placements:",
        "        topic_application: { anchor: supervisor, align: right, width_mm: 28 }  # as in the template",
        "      default_dates:",
        "        topic_application:",
        "          - { anchor: supervisor.day }",
        "",
      ].join("\n"),
    );
  });

  it("ручное место и метка даты относительно якоря сборки, мм этой сборки в комментарии", () => {
    const preset = build({
      texts: ANCHOR_TEXTS,
      documents: [{ id: "topic_application" }],
      anchors: { topic_application: BUILD },
      placements: {
        topic_application: {
          supervisor: place(168, 177, 28, {
            origin: "manual",
            dates: [
              {
                page: 1,
                x_mm: 121,
                y_mm: 195,
                width_mm: 6,
                height_mm: 5,
                format: "day",
                align: "center",
              },
              {
                page: 1,
                x_mm: 130,
                y_mm: 195,
                width_mm: 20,
                height_mm: 5,
                format: "month_word",
                align: "center",
              },
            ],
          }),
        },
      },
    });
    expect(preset.yaml).toContain(
      "        topic_application: { anchor: supervisor, align: left, dx_mm: -1.5, dy_mm: -9.8, width_mm: 28 }  # by the build: 1, 168, 177, 28",
    );
    // Метка на линии (верх на высоту выше), по центру линии: только сдвиг и ширина.
    expect(preset.yaml).toContain(
      "          - { anchor: supervisor.day, width_mm: 6 }  # by the build: 1, 121, 195, 6, 5",
    );
    // Якоря месяца в сборке нет: метка в мм с пометкой.
    expect(preset.yaml).toContain(
      "          - { page: 1, x_mm: 130, y_mm: 195, width_mm: 20, height_mm: 5, format: month_word }  # no anchor",
    );
    expect(preset.yaml).toContain("# Taken from the build of 13 Nov.");
  });

  it("якоря неизвестны или якоря нет на странице: мм с комментарием, без строки о сборке", () => {
    const preset = build({
      texts: ANCHOR_TEXTS,
      documents: [{ id: "topic_application" }, { id: "report" }],
      anchors: { topic_application: null, report: BUILD },
      placements: {
        topic_application: { supervisor: place(163, 168, 40) },
        report: { author: place(150, 250, 30, { page: 2 }) },
      },
    });
    expect(preset.yaml).toContain(
      "topic_application: { page: 1, x_mm: 163, y_mm: 168, width_mm: 40 }  # no anchor",
    );
    expect(preset.yaml).toContain(
      "report: { page: 2, x_mm: 150, y_mm: 250, width_mm: 30 }  # no anchor",
    );
    expect(preset.yaml).not.toContain("Taken from the build");
  });
});
