import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { SignaturesStateResponse } from "@shared/api/types";
import { DocPlacementPanel, type PlacementSlot } from "./DocPlacementPanel";

// «Придержано маршрутом» и «Показать» (docs/design/signing-route.md, 5.6): после отмены маршрута
// картинка того, кто не согласовал, остаётся скрытой, пока её не покажут явно.

const DOC = "topic_application";

const slot = (id: string, label: string): PlacementSlot => ({
  id,
  label: { ru: label, en: label },
  applies_to: [DOC],
  default_placement: { page: 1, x_mm: 10, y_mm: 10, width_mm: 40 },
});

const state = (
  withheld: Record<string, string[]>,
): SignaturesStateResponse => ({
  slots: {
    author: {
      png_path: ".hse-studio/signatures/author.png",
      natural_width_px: 120,
      natural_height_px: 40,
      signing_identity_id: null,
      sign_mode: "image",
      sign_reason: "",
      signer: null,
    },
    supervisor: {
      png_path: ".hse-studio/signatures/supervisor.png",
      natural_width_px: 120,
      natural_height_px: 40,
      signing_identity_id: null,
      sign_mode: "image",
      sign_reason: "",
      signer: null,
    },
  },
  placements: {},
  withheld,
});

const mount = (
  withheld: Record<string, string[]>,
  onReleaseWithheld?: (slotId: string) => void,
) =>
  render(
    <I18nextProvider i18n={i18n}>
      <DocPlacementPanel
        projectId="p1"
        docId={DOC}
        pdfAvailable
        slotDefs={[
          slot("author", "Студент"),
          slot("supervisor", "Научный руководитель"),
        ]}
        state={state(withheld)}
        lang="ru"
        currentPage={1}
        pageCount={1}
        personNameForSlot={() => null}
        onPlacementChange={vi.fn()}
        onJumpToPage={vi.fn()}
        onOpenProjectSignatures={vi.fn()}
        onSlotModeChange={vi.fn()}
        {...(onReleaseWithheld ? { onReleaseWithheld } : {})}
      />
    </I18nextProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

describe("Подписи документа: картинка, придержанная маршрутом", () => {
  it("пометка «Придержано маршрутом» и «Показать» только у придержанного слота", async () => {
    const release = vi.fn();
    const u = userEvent.setup();
    mount({ [DOC]: ["supervisor"], other_doc: ["author"] }, release);

    expect(screen.getByTestId("doc-withheld-supervisor")).toHaveTextContent(
      "Придержано маршрутом",
    );
    // Придержание у другого документа этот документ не касается.
    expect(screen.queryByTestId("doc-withheld-author")).toBeNull();
    await u.click(screen.getByTestId("doc-withheld-show-supervisor"));
    expect(release).toHaveBeenCalledWith("supervisor");
  });

  it("без обработчика пометка видна, кнопки нет", () => {
    mount({ [DOC]: ["supervisor"] });
    expect(screen.getByTestId("doc-withheld-supervisor")).toBeInTheDocument();
    expect(screen.queryByTestId("doc-withheld-show-supervisor")).toBeNull();
  });

  it("ничего не придержано: пометок нет", () => {
    mount({}, vi.fn());
    expect(screen.queryByTestId(/^doc-withheld-/)).toBeNull();
  });
});

// «Подпись необязательна» (docs/design/signing-route.md, 13.9): строка с галочкой на каждую точку
// слота, причина, почему отметить нельзя, пропуск и возврат в маршрут.

const POINT = {
  id: "topic-approval",
  name: { ru: "Заявка на тему КП", en: "Topic application" },
};

const optionalSlots = (): PlacementSlot[] => [
  {
    ...slot("author", "Студент"),
    required: true,
    required_by: { [DOC]: [POINT] },
  },
  {
    ...slot("supervisor", "Научный руководитель"),
    required_by: { [DOC]: [POINT] },
  },
  {
    ...slot("academic_supervisor", "Академический руководитель"),
    required_by: {},
    extra_by: { [DOC]: [POINT] },
  },
];

const mountOptional = (
  extra: Partial<SignaturesStateResponse>,
  control: Partial<{
    canEdit: boolean;
    isSigned: (slotId: string) => boolean;
    onChange: (slotId: string, profileId: string, optional: boolean) => void;
  }> = {},
  locked = false,
) =>
  render(
    <I18nextProvider i18n={i18n}>
      <DocPlacementPanel
        projectId="p1"
        docId={DOC}
        pdfAvailable
        slotDefs={optionalSlots()}
        state={{ ...state({}), ...extra }}
        lang="ru"
        currentPage={1}
        pageCount={1}
        personNameForSlot={() => null}
        onPlacementChange={vi.fn()}
        onJumpToPage={vi.fn()}
        onOpenProjectSignatures={vi.fn()}
        onSlotModeChange={vi.fn()}
        locked={locked}
        optionalControl={{
          canEdit: control.canEdit ?? true,
          isSigned: control.isSigned ?? (() => false),
          isPending: () => false,
          onChange: control.onChange ?? vi.fn(),
        }}
      />
    </I18nextProvider>,
  );

const box = (slotId: string) =>
  screen.getByTestId(`doc-optional-${slotId}-${POINT.id}`);

describe("Подписи документа: «Подпись необязательна»", () => {
  it("галочка у каждой точки слота, у слота сверх точки с её названием", async () => {
    const onChange = vi.fn();
    const u = userEvent.setup();
    mountOptional({}, { onChange });

    expect(screen.getByTestId("doc-optional-supervisor")).toHaveTextContent(
      "Подпись необязательна на этой точке",
    );
    expect(
      screen.getByTestId("doc-optional-academic_supervisor"),
    ).toHaveTextContent("Подпись необязательна на точке «Заявка на тему КП»");
    await u.click(box("academic_supervisor"));
    expect(onChange).toHaveBeenCalledWith(
      "academic_supervisor",
      POINT.id,
      true,
    );
  });

  it("отметить нельзя: шаблон требует, подпись стоит, нет прав", () => {
    mountOptional({}, { isSigned: (id) => id === "supervisor" });
    expect(box("author")).toBeDisabled();
    expect(screen.getByTestId("doc-optional-author")).toHaveTextContent(
      "Эту подпись требует шаблон: сделать её необязательной нельзя",
    );
    expect(box("supervisor")).toBeDisabled();
    expect(screen.getByTestId("doc-optional-supervisor")).toHaveTextContent(
      "Подпись уже стоит",
    );
    expect(box("academic_supervisor")).toBeEnabled();
  });

  it("без прав галочка выключена и снять её тоже нельзя", () => {
    mountOptional(
      { optional: { [DOC]: { [POINT.id]: ["academic_supervisor"] } } },
      { canEdit: false },
    );
    expect(box("academic_supervisor")).toBeChecked();
    expect(box("academic_supervisor")).toBeDisabled();
    expect(
      screen.getByTestId("doc-optional-academic_supervisor"),
    ).toHaveTextContent(
      "Нет прав: отмечать может тот, кто отправляет на подписание",
    );
  });

  it("отмеченную подпись снять можно, даже если она уже стоит", () => {
    mountOptional(
      { optional: { [DOC]: { [POINT.id]: ["supervisor"] } } },
      { isSigned: () => true },
    );
    expect(box("supervisor")).toBeChecked();
    expect(box("supervisor")).toBeEnabled();
    expect(screen.getByTestId("doc-optional-supervisor")).toHaveTextContent(
      "Автор маршрута сможет пропустить этого подписанта",
    );
  });

  it("пропущенный слот: пометка, плашка в B, после снятия отметки вернётся в маршрут", () => {
    const skipped = {
      [DOC]: {
        academic_supervisor: {
          profile_id: POINT.id,
          route_id: "sr_1",
          round: 1,
          at: "2026-11-13T10:00:00Z",
          keep_mark: true,
        },
      },
    };
    const { unmount } = mountOptional({
      optional: { [DOC]: { [POINT.id]: ["academic_supervisor"] } },
      skipped,
    });
    const row = screen.getByTestId("doc-optional-academic_supervisor");
    expect(
      screen.getByTestId("doc-skipped-academic_supervisor"),
    ).toHaveTextContent("Не требуется: пропущено автором 13.11");
    expect(row).toHaveTextContent("Плашка осталась в зафиксированном PDF");
    expect(row).not.toHaveTextContent("Вернётся в маршрут");
    unmount();

    mountOptional({ optional: {}, skipped });
    expect(
      screen.getByTestId("doc-optional-academic_supervisor"),
    ).toHaveTextContent("Вернётся в маршрут при следующей отправке");
  });

  it("на подписании правки слота закрыты, галочка открыта", () => {
    mountOptional({}, {}, true);
    expect(
      screen.getByTestId("doc-slot-edit-academic_supervisor"),
    ).toHaveAttribute("inert");
    expect(box("academic_supervisor")).toBeEnabled();
    expect(box("academic_supervisor").closest("[inert]")).toBeNull();
  });

  it("без управления галочек нет", () => {
    mount({});
    expect(screen.queryByTestId(/^doc-optional-/)).toBeNull();
  });
});

// Маршрут из шаблона (docs/design/signing-route.md, 15.7): пометка места и «Вернуть место из
// шаблона» у включённого места; затравка и место как в шаблоне без кнопки.

describe("Подписи документа: место из шаблона", () => {
  const placed = (
    origin: "pack" | "seed" | "manual",
    presetAvailable = true,
  ) => ({
    enabled: true,
    page: 1,
    x_mm: 10,
    y_mm: 10,
    width_mm: 40,
    sign_date: null,
    dates: [],
    signed_at: null,
    origin,
    preset_available: presetAvailable,
    source: origin === "manual" ? null : ("mm" as const),
    anchor: null,
  });

  const mountPlaces = (
    placements: SignaturesStateResponse["placements"],
    control: {
      canRestore: boolean;
      onRestore: (slotId: string) => void;
      ownPdf?: boolean;
    },
  ) =>
    render(
      <I18nextProvider i18n={i18n}>
        <DocPlacementPanel
          projectId="p1"
          docId={DOC}
          pdfAvailable
          slotDefs={[
            slot("author", "Студент"),
            {
              ...slot("supervisor", "Научный руководитель"),
              // Место пака научрука на строке шаблона, без запасного места в мм.
              default_placements: {
                [DOC]: {
                  source: "anchor",
                  anchor: "supervisor",
                  align: "center",
                  dx_mm: 0,
                  dy_mm: -10,
                  width_mm: null,
                  fallback: null,
                },
              },
            },
          ]}
          state={{ ...state({}), placements }}
          lang="ru"
          currentPage={1}
          pageCount={1}
          personNameForSlot={() => null}
          onPlacementChange={vi.fn()}
          onJumpToPage={vi.fn()}
          onOpenProjectSignatures={vi.fn()}
          onSlotModeChange={vi.fn()}
          locked
          placeControl={{
            canRestore: control.canRestore,
            ownPdf: control.ownPdf ?? false,
            isRestoring: () => false,
            onRestore: control.onRestore,
          }}
        />
      </I18nextProvider>,
    );

  it("«Место изменено» с кнопкой, «Место из шаблона» без неё; под маршрутом кнопка открыта", async () => {
    const restore = vi.fn();
    const u = userEvent.setup();
    mountPlaces(
      { [DOC]: { author: placed("pack"), supervisor: placed("manual") } },
      { canRestore: true, onRestore: restore },
    );
    expect(screen.getByTestId("place-origin-author")).toHaveTextContent(
      "Место из шаблона",
    );
    expect(screen.queryByTestId("place-restore-author")).toBeNull();
    expect(screen.getByTestId("place-origin-supervisor")).toHaveTextContent(
      "Место изменено",
    );
    // Документ на подписании (`locked`): правки слота закрыты, а «Вернуть место» открыта.
    await u.click(screen.getByTestId("place-restore-supervisor"));
    expect(restore).toHaveBeenCalledWith("supervisor");
  });

  it("без прав кнопки нет; без места в шаблоне и у выключенного места пометки нет", () => {
    mountPlaces(
      {
        [DOC]: {
          author: { ...placed("seed"), enabled: false },
          supervisor: placed("manual", false),
        },
      },
      { canRestore: false, onRestore: vi.fn() },
    );
    expect(screen.queryByTestId("place-origin-author")).toBeNull();
    expect(screen.queryByTestId("place-origin-supervisor")).toBeNull();
  });

  it("ручное место без прав: пометка есть, кнопки нет", () => {
    mountPlaces(
      { [DOC]: { supervisor: placed("manual") } },
      { canRestore: false, onRestore: vi.fn() },
    );
    expect(screen.getByTestId("place-origin-supervisor")).toHaveTextContent(
      "Место изменено",
    );
    expect(screen.queryByTestId("place-restore-supervisor")).toBeNull();
  });

  // Места на строках шаблона (15.17.14): уточнение пометки и подсказки вместо кнопки.
  const onAnchor = (
    origin: "pack" | "seed" | "manual",
    state: "found" | "missing" | "unknown",
    enabled = true,
  ) => ({
    ...placed(origin),
    enabled,
    source: origin === "pack" ? ("anchor" as const) : null,
    anchor: { id: "supervisor", state },
  });

  it("место на якоре: «Место по строке шаблона»; нет строки: подсказка вместо кнопки и у выключенного", () => {
    mountPlaces(
      {
        [DOC]: {
          author: placed("pack"),
          supervisor: onAnchor("manual", "missing"),
        },
      },
      { canRestore: true, onRestore: vi.fn() },
    );
    expect(screen.getByTestId("place-origin-author")).toHaveTextContent(
      "Место из шаблона",
    );
    expect(screen.queryByTestId("place-anchor-author")).toBeNull();
    expect(screen.getByTestId("place-origin-supervisor")).toHaveTextContent(
      "Место изменено",
    );
    expect(screen.queryByTestId("place-restore-supervisor")).toBeNull();
    expect(screen.getByTestId("place-anchor-supervisor")).toHaveTextContent(
      "В собранном документе нет строки для этой подписи. Проверьте данные проекта или поставьте место вручную",
    );
  });

  it("строка есть: «по строке шаблона»; якоря неизвестны без запасного места: «появится после сборки»", () => {
    const { unmount } = mountPlaces(
      { [DOC]: { supervisor: onAnchor("pack", "found") } },
      { canRestore: true, onRestore: vi.fn() },
    );
    expect(screen.getByTestId("place-origin-supervisor")).toHaveTextContent(
      "Место по строке шаблона",
    );
    expect(screen.queryByTestId("place-anchor-supervisor")).toBeNull();
    unmount();
    mountPlaces(
      { [DOC]: { supervisor: onAnchor("seed", "unknown", false) } },
      { canRestore: true, onRestore: vi.fn() },
    );
    expect(screen.queryByTestId("place-origin-supervisor")).toBeNull();
    expect(screen.getByTestId("place-anchor-supervisor")).toHaveTextContent(
      "Место из шаблона появится после сборки документа",
    );
  });

  it("свой PDF: у места на якоре подсказка вместо «Вернуть место из шаблона»", () => {
    mountPlaces(
      { [DOC]: { supervisor: onAnchor("manual", "unknown") } },
      { canRestore: true, onRestore: vi.fn(), ownPdf: true },
    );
    expect(screen.queryByTestId("place-restore-supervisor")).toBeNull();
    expect(screen.getByTestId("place-anchor-supervisor")).toHaveAttribute(
      "data-note",
      "own_pdf",
    );
    expect(screen.getByTestId("place-anchor-supervisor")).toHaveTextContent(
      "У загруженного PDF нет строк шаблона: поставьте место вручную",
    );
  });
});
