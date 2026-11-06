import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@shared/lib/i18n";
import type { OldVersionItem, OldVersions } from "@entities/docker-system";
import { DiskOldVersions } from "./DiskOldVersions";

const image = (ref: string, size: number, version = ""): OldVersionItem => ({
  kind: "studio_image",
  ref,
  version,
  size_bytes: size,
  created: "1 month ago",
});

const OLD: OldVersions = {
  current_version: "cur",
  rollback: image("reg/studio:prev", 3_000_000_000),
  items: [
    image("reg/studio:older", 2_000_000_000),
    {
      kind: "container",
      ref: "hse-studio-updater",
      version: "",
      size_bytes: 1000,
      created: "",
    },
  ],
  reclaimable_bytes: 2_000_001_000,
  rollback_bytes: 3_000_000_000,
};

const mount = (oldVersions: OldVersions, onClean = vi.fn(), busy = false) => {
  render(
    <DiskOldVersions oldVersions={oldVersions} busy={busy} onClean={onClean} />,
  );
  return onClean;
};

describe("DiskOldVersions", () => {
  afterEach(cleanup);

  it("lists old items and tells the rollback version is kept", () => {
    mount(OLD);
    expect(screen.getByText("reg/studio:older")).toBeInTheDocument();
    expect(screen.getByText("hse-studio-updater")).toBeInTheDocument();
    expect(screen.getByText(/reg\/studio:prev/)).toBeInTheDocument();
  });

  it("asks for confirmation and keeps the rollback unless chosen on purpose", async () => {
    const user = userEvent.setup();
    const onClean = mount(OLD);
    await user.click(
      screen.getByRole("button", {
        name: /Удалить старые версии|Remove old versions/,
      }),
    );
    const dialog = screen.getByRole("dialog");
    expect(onClean).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("checkbox")).not.toBeChecked();
    await user.click(
      within(dialog).getByRole("button", { name: /^(Удалить|Remove) ·/ }),
    );
    expect(onClean).toHaveBeenCalledWith(false);
  });

  it("removes the rollback only after the explicit checkbox", async () => {
    const user = userEvent.setup();
    const onClean = mount(OLD);
    await user.click(
      screen.getByRole("button", {
        name: /Удалить старые версии|Remove old versions/,
      }),
    );
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox"));
    expect(
      within(dialog).getAllByText("reg/studio:prev").length,
    ).toBeGreaterThan(0);
    await user.click(
      within(dialog).getByRole("button", { name: /^(Удалить|Remove) ·/ }),
    );
    expect(onClean).toHaveBeenCalledWith(true);
  });

  it("disables the button when nothing is old or a cleanup is running", () => {
    mount({ ...OLD, items: [], reclaimable_bytes: 0 });
    expect(
      screen.getByRole("button", {
        name: /Удалить старые версии|Remove old versions/,
      }),
    ).toBeDisabled();
    cleanup();
    mount(OLD, vi.fn(), true);
    expect(
      screen.getByRole("button", {
        name: /Удалить старые версии|Remove old versions/,
      }),
    ).toBeDisabled();
  });
});
