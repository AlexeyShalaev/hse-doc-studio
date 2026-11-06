import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@shared/lib/i18n";
import type { DockerUsage } from "@entities/docker-system";
import { StartupChecks } from "./StartupChecks";

const GIB = 1024 ** 3;
const state = vi.hoisted(() => ({
  usage: undefined as DockerUsage | undefined,
  warnGb: 5,
}));

vi.mock("@features/check-update", () => ({
  useCheckUpdate: () => ({ updateAvailable: false, latestVersion: "" }),
}));
vi.mock("@entities/app-settings", () => ({
  useAppSettings: () => ({ data: { disk_usage_warn_gb: state.warnGb } }),
}));
vi.mock("@entities/docker-system", () => ({
  useDockerUsage: () => ({ data: state.usage }),
}));

const usage = (cleanable: number, old: number): DockerUsage =>
  ({
    available: true,
    cleanable_bytes: cleanable,
    old_versions: { reclaimable_bytes: old },
  }) as DockerUsage;

const mount = () =>
  render(
    <MemoryRouter>
      <StartupChecks />
    </MemoryRouter>,
  );

describe("StartupChecks disk banner", () => {
  afterEach(cleanup);

  it("names old versions once they alone pass the shared threshold", () => {
    state.usage = usage(8 * GIB, 6 * GIB);
    mount();
    expect(
      screen.getByText(
        /Старые версии занимают место|Old versions are taking space/,
      ),
    ).toBeInTheDocument();
  });

  it("keeps the generic warning when old versions are below the threshold", () => {
    state.usage = usage(8 * GIB, 1 * GIB);
    mount();
    expect(
      screen.getByText(
        /Docker занял много места|Docker is using a lot of space/,
      ),
    ).toBeInTheDocument();
  });

  it("stays silent below the threshold or when the warning is off", () => {
    state.usage = usage(2 * GIB, 2 * GIB);
    const { container } = mount();
    expect(container).toBeEmptyDOMElement();
    cleanup();
    state.warnGb = 0;
    state.usage = usage(80 * GIB, 80 * GIB);
    expect(mount().container).toBeEmptyDOMElement();
    state.warnGb = 5;
  });
});
