import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";
import { PackPresetDialog } from "./PackPresetDialog";

const data = vi.hoisted(() => {
  const placements: Record<string, Record<string, unknown>> = {};
  const anchors: Record<string, unknown> = {};
  return { placements, anchors };
});

vi.mock("@entities/project", () => ({
  useProject: () => ({
    data: {
      id: "p1",
      name: "Секретный проект",
      lock: {
        pack_id: "hse-cs-sse",
        template_id: "coursework",
        version: "2026.1.3",
      },
      supervisor: { name: "Петров Пётр Петрович" },
    },
  }),
}));
vi.mock("@entities/signature", () => ({
  useSignaturesState: () => ({
    data: {
      placements: data.placements,
      runtime_slots: [],
      anchors: data.anchors,
    },
  }),
}));
vi.mock("@entities/document", () => ({
  useDocuments: () => ({
    data: [
      { id: "project_proposal", last_compile_at: "2026-11-13T09:30:00Z" },
      { id: "topic_application" },
    ],
  }),
}));
vi.mock("@entities/template-catalog", () => ({
  useVersionDetail: () => ({
    data: {
      version: "2026.1.3",
      supported_staffing: ["solo"],
      documents: [
        { id: "project_proposal", scope: "shared" },
        { id: "topic_application", scope: "shared" },
      ],
      signatures: {
        slots: [
          {
            id: "supervisor",
            applies_to: ["project_proposal", "topic_application"],
            per_author: false,
          },
        ],
      },
    },
  }),
}));

const place = (x_mm: number, y_mm: number) => ({
  enabled: true,
  page: 1,
  x_mm,
  y_mm,
  width_mm: 40,
  dates: [],
});

describe("PackPresetDialog", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    data.placements = {
      project_proposal: {
        supervisor: place(80.4, 139.2),
        "custom-dean": place(10, 10),
      },
      topic_application: { supervisor: place(163, 168) },
    };
    data.anchors = {};
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("копирует YAML этого документа и показывает его в окне", async () => {
    userEvent.setup();
    const success = vi.spyOn(toast, "success").mockReturnValue("t");
    render(
      <PackPresetDialog
        isOpen
        onClose={vi.fn()}
        projectId="p1"
        docId="project_proposal"
      />,
    );
    const field = await screen.findByLabelText("YAML пресета");
    const yaml = (field as HTMLTextAreaElement).value;
    expect(yaml).toContain(
      "# Пресет мест подписей для пака hse-cs-sse, шаблон coursework, собран на версии 2026.1.3.",
    );
    expect(yaml).toContain(
      "project_proposal: { page: 1, x_mm: 80, y_mm: 139, width_mm: 40 }",
    );
    expect(yaml).not.toContain("topic_application");
    // Ни людей, ни названия проекта во фрагменте.
    expect(yaml).not.toContain("Петров");
    expect(yaml).not.toContain("Секретный");
    await waitFor(() => {
      expect(success).toHaveBeenCalledWith("Пресет шаблона скопирован");
    });
    expect(await navigator.clipboard.readText()).toBe(yaml);
    expect(screen.getByTestId("pack-preset-warnings")).toHaveTextContent(
      "Подпись custom-dean не из пака: пропущена.",
    );
  });

  it("по выбору берёт все документы проекта", async () => {
    const user = userEvent.setup();
    vi.spyOn(toast, "success").mockReturnValue("t");
    render(
      <PackPresetDialog
        isOpen
        onClose={vi.fn()}
        projectId="p1"
        docId="project_proposal"
      />,
    );
    await user.click(
      await screen.findByRole("radio", { name: "Все документы проекта" }),
    );
    const field = screen.getByLabelText<HTMLTextAreaElement>("YAML пресета");
    expect(field.value).toContain(
      "topic_application: { page: 1, x_mm: 163, y_mm: 168, width_mm: 40 }",
    );
  });

  it("без мест говорит, что переносить нечего, и ничего не копирует", async () => {
    userEvent.setup();
    const success = vi.spyOn(toast, "success").mockReturnValue("t");
    data.placements = {
      project_proposal: { supervisor: { ...place(80, 139), enabled: false } },
    };
    render(
      <PackPresetDialog
        isOpen
        onClose={vi.fn()}
        projectId="p1"
        docId="project_proposal"
      />,
    );
    expect(await screen.findByText(/Переносить нечего/)).toBeInTheDocument();
    expect(screen.queryByLabelText("YAML пресета")).toBeNull();
    expect(screen.getByTestId("pack-preset-warnings")).toHaveTextContent(
      "1 выключенное место пропущено.",
    );
    expect(success).not.toHaveBeenCalled();
  });

  it("говорит по-английски в английском интерфейсе", async () => {
    userEvent.setup();
    vi.spyOn(toast, "success").mockReturnValue("t");
    await i18n.changeLanguage("en");
    render(
      <PackPresetDialog
        isOpen
        onClose={vi.fn()}
        projectId="p1"
        docId="project_proposal"
      />,
    );
    const field = await screen.findByLabelText("Preset YAML");
    expect((field as HTMLTextAreaElement).value).toContain(
      "# Signature place preset for pack hse-cs-sse",
    );
  });

  it("ручное место выводит относительно якоря сборки, без якорей в мм с пометкой", async () => {
    userEvent.setup();
    vi.spyOn(toast, "success").mockReturnValue("t");
    data.anchors = {
      project_proposal: {
        build: "5f0c2b8e1d7a4c3b",
        items: [
          {
            id: "supervisor",
            kind: "sign",
            page: 1,
            x_mm: 80,
            y_mm: 150,
            width_mm: 40,
          },
        ],
        problems: [],
      },
      topic_application: null,
    };
    render(
      <PackPresetDialog
        isOpen
        onClose={vi.fn()}
        projectId="p1"
        docId="project_proposal"
      />,
    );
    const field =
      await screen.findByLabelText<HTMLTextAreaElement>("YAML пресета");
    expect(field.value).toContain("# Собрано по сборке 13 нояб. 2026 г.");
    expect(field.value).toContain(
      "project_proposal: { anchor: supervisor, align: left, dx_mm: 0.4, dy_mm: -10.8, width_mm: 40 }  # по сборке: 1, 80, 139, 40",
    );
  });
});
