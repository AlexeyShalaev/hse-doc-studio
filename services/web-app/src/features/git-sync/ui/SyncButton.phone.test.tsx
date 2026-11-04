import { cleanup, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { installViewport } from "@shared/lib/viewport/testing";
import { Popover } from "@shared/ui/Popover";
import { connected } from "../testing/statusFactory";
import { deriveSyncUi } from "../model/syncUi.model";
import { useSyncText } from "../model/useSyncText";
import { SyncButton } from "./SyncButton";

const NOW = Date.parse("2026-10-26T10:30:00Z");

const Harness = ({
  onPrimary,
  onToggleDetails,
}: {
  onPrimary: () => void;
  onToggleDetails: () => void;
}) => {
  const ui = deriveSyncUi(connected(), { online: true, readOnly: false });
  const text = useSyncText(ui, NOW);
  return (
    <Popover open={false}>
      <SyncButton
        ui={ui}
        text={text}
        isOpen={false}
        onPrimary={onPrimary}
        onToggleDetails={onToggleDetails}
      />
    </Popover>
  );
};

describe("SyncButton on a phone", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    viewport?.restore();
    viewport = undefined;
  });

  it("is one button that opens the details sheet instead of running the sync", async () => {
    viewport = installViewport(390);
    const onPrimary = vi.fn();
    const onToggleDetails = vi.fn();
    render(<Harness onPrimary={onPrimary} onToggleDetails={onToggleDetails} />);
    expect(document.querySelector(".sync-chevron")).toBeNull();
    await userEvent.setup().click(document.querySelector(".sync-main")!);
    expect(onToggleDetails).toHaveBeenCalledOnce();
    expect(onPrimary).not.toHaveBeenCalled();
  });

  it("keeps the split button on a desktop: the main part runs the action", async () => {
    viewport = installViewport(1360);
    const onPrimary = vi.fn();
    const onToggleDetails = vi.fn();
    render(<Harness onPrimary={onPrimary} onToggleDetails={onToggleDetails} />);
    expect(document.querySelector(".sync-chevron")).not.toBeNull();
    await userEvent.setup().click(document.querySelector(".sync-main")!);
    expect(onPrimary).toHaveBeenCalledOnce();
  });
});
