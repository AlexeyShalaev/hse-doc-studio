import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@shared/lib/i18n";
import type { DockerUsage } from "@entities/docker-system";

const USAGE: DockerUsage = {
  available: true,
  images: [
    {
      reference: "reg/compile:1",
      repository: "reg/compile",
      tag: "1",
      size_bytes: 4_000_000_000,
      created: "1 month ago",
      in_use: true,
      category: "compile",
      dangling: false,
      protected: true,
    },
    {
      reference: "reg/ollama:1",
      repository: "reg/ollama",
      tag: "1",
      size_bytes: 2_000_000_000,
      created: "2 months ago",
      in_use: false,
      category: "ai",
      dangling: false,
      protected: false,
    },
    {
      reference: "<none>:<none>",
      repository: "<none>",
      tag: "<none>",
      size_bytes: 100_000_000,
      created: "3 months ago",
      in_use: false,
      category: "dangling",
      dangling: true,
      protected: false,
    },
  ],
  containers: [
    {
      name: "hse-studio-compile",
      image: "reg/compile:1",
      state: "exited",
      status: "Exited (0)",
      size_bytes: 50_000_000,
      managed: true,
    },
  ],
  volumes: [
    { name: "texmf", size_bytes: 300_000_000, links: 1, managed: true },
  ],
  images_total_bytes: 6_100_000_000,
  containers_total_bytes: 50_000_000,
  volumes_total_bytes: 300_000_000,
  build_cache_bytes: 700_000_000,
  build_cache_reclaimable_bytes: 500_000_000,
  build_cache_count: 12,
  total_bytes: 7_150_000_000,
  cleanable_bytes: 2_650_000_000,
  old_versions: {
    current_version: "0.21.0",
    rollback: null,
    items: [],
    reclaimable_bytes: 0,
    rollback_bytes: 0,
  },
};

const refetch = vi.fn();

vi.mock("@entities/docker-system", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "@entities/docker-system",
  );
  return {
    ...actual,
    useDockerUsage: () => ({
      data: USAGE,
      isLoading: false,
      isFetching: false,
      refetch,
    }),
    useCleanupJob: () => ({ data: { job: null } }),
    useStartCleanup: () => ({ mutate: vi.fn(), isPending: false }),
    useCancelCleanup: () => ({ mutate: vi.fn(), isPending: false }),
  };
});

vi.mock("@entities/app-settings", () => ({
  useAppSettings: () => ({ data: { disk_usage_warn_gb: 10 } }),
  useUpdateAppSettings: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "@tanstack/react-query",
  );
  return { ...actual, useQueryClient: () => ({ invalidateQueries: vi.fn() }) };
});

import { DiskUsageSection } from "./DiskUsageSection";

afterEach(cleanup);

describe("DiskUsageSection", () => {
  it("shows the total and a legend row per non-empty category in fixed order", () => {
    render(<DiskUsageSection />);

    // 4e9 compile + 2e9 ai + 0.7e9 build cache + (0.1e9 dangling + 0.05e9
    // containers + 0.3e9 volumes) runtime, shown in binary units.
    expect(screen.getByText("Занято программой: 6.66 GB")).toBeTruthy();
    expect(screen.getByText("можно освободить: 2.47 GB")).toBeTruthy();

    const legend = screen.getByTestId("disk-usage-legend");
    const labels = within(legend)
      .getAllByTestId("disk-usage-legend-item")
      .map((item) => item.textContent);
    expect(labels).toEqual([
      "LaTeX / TeX Live3.73 GB",
      "Локальные модели (Ollama)1.86 GB",
      "Кэш сборки668 MB",
      "Контейнеры и тома429 MB",
    ]);

    const bar = screen.getByTestId("disk-usage-bar");
    expect(bar.children).toHaveLength(4);
    expect((bar.children[0] as HTMLElement).style.background).toBe(
      "var(--chart-1)",
    );
    expect((bar.children[1] as HTMLElement).style.background).toBe(
      "var(--chart-4)",
    );
  });
});
