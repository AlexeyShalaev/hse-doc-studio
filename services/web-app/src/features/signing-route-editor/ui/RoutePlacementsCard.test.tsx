import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { SignaturesStateResponse } from "@shared/api/types";
import type { RoutePreset } from "@entities/signing-route";
import {
  SR_DOC,
  makeRouteParticipant,
  makeSigningRoute,
} from "@entities/signing-route/testing";
import { RoutePlacementsCard } from "./RoutePlacementsCard";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

vi.mock("@features/signature-stamper", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  PdfStampEditor: () => <div data-testid="stamp-editor" />,
}));

// «Где подписи» маршрута из шаблона (docs/design/signing-route.md, 15.7): слот сверх точки,
// добавленный шаблоном, с причиной условия, отметка «необязательна» «по шаблону».

const DOC = SR_DOC.doc_id;
const COMPANY = { person: "supervisor", role: "company" as const };

const PRESET: RoutePreset = {
  version: "2026.1.4",
  base_version: "2026.1.4",
  steps: [["author"], ["supervisor"], ["academic_supervisor"]],
  extra_slots: [{ doc_id: DOC, slot_id: "academic_supervisor", when: COMPANY }],
  optional: [{ doc_id: DOC, slot_id: "academic_supervisor" }],
  skipped_by_condition: [],
  differs: [],
};

const ROUTE = makeSigningRoute({
  status: "draft",
  phase: null,
  docs: [
    {
      ...SR_DOC,
      frozen: false,
      sent: null,
      changed: false,
      slots: [
        {
          slot_id: "supervisor",
          label: { ru: "Научный руководитель" },
          participant_id: "srp_supervisor",
          extra: false,
          optional: false,
          status: "pending",
          added_by: null,
          preset_optional: false,
        },
        {
          slot_id: "academic_supervisor",
          label: { ru: "Академический руководитель" },
          participant_id: "srp_academic",
          extra: true,
          optional: true,
          status: "pending",
          added_by: "pack",
          preset_optional: true,
        },
      ],
    },
  ],
  steps: [
    [makeRouteParticipant({ id: "srp_supervisor", persona: "supervisor" })],
    [
      makeRouteParticipant({
        id: "srp_academic",
        persona: "academic_supervisor",
        name: "Сидоров С. С.",
      }),
    ],
  ],
  preset: PRESET,
});

const runtime = (id: string) => ({
  id,
  label: { ru: id },
  applies_to: [DOC],
  required_by: {},
  default_placement: { page: 1, x_mm: 10, y_mm: 10, width_mm: 40 },
});

const STATE: SignaturesStateResponse = {
  slots: {},
  placements: {},
  runtime_slots: [runtime("supervisor"), runtime("academic_supervisor")],
};

const mount = (preset: RoutePreset | null) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={new QueryClient()}>
        <RoutePlacementsCard
          projectId="p1"
          route={ROUTE}
          preset={preset}
          preview={undefined}
          editable
          busy={false}
          state={STATE}
          documents={[]}
          personaLabel={(persona) => persona}
          onAddExtra={vi.fn()}
          onRemoveExtra={vi.fn()}
          onSetOptional={vi.fn()}
        />
      </QueryClientProvider>
    </I18nextProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

afterEach(() => {
  cleanup();
});

describe("«Где подписи»: маршрут из шаблона", () => {
  it("слот добавлен шаблоном: причина условия; отметка «по шаблону»", () => {
    mount(PRESET);
    const row = screen.getByTestId("route-slot-academic_supervisor");
    expect(row).toHaveTextContent(
      "добавлена шаблоном: научный руководитель не из ВШЭ",
    );
    expect(row).not.toHaveTextContent("добавлена вами");
    expect(
      within(row).getByTestId("route-optional-academic_supervisor-preset"),
    ).toHaveTextContent("по шаблону");
    // У пары точки ни пометки сверх точки, ни «по шаблону».
    const supervisor = screen.getByTestId("route-slot-supervisor");
    expect(supervisor).not.toHaveTextContent("добавлена");
    expect(
      within(supervisor).queryByTestId("route-optional-supervisor-preset"),
    ).toBeNull();
  });

  it("на английском: условие переводится по коду", async () => {
    await i18n.changeLanguage("en");
    mount(PRESET);
    expect(
      screen.getByTestId("route-slot-academic_supervisor"),
    ).toHaveTextContent(
      "added by the template: the supervisor is not from HSE",
    );
  });

  it("без пресета причины нет", () => {
    mount(null);
    const row = screen.getByTestId("route-slot-academic_supervisor");
    expect(row).toHaveTextContent("добавлена шаблоном");
    expect(row).not.toHaveTextContent("не из ВШЭ");
  });
});
