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
