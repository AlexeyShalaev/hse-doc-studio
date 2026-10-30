import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { CompilePlacement, ProjectBuildRunners } from "@entities/runner";
import { placementView } from "./lib/placementView";
import { BuildPlacementChip } from "./ui/BuildPlacementChip";
import { CompileWaitNotice } from "./ui/CompileWaitNotice";
import { ProjectBuildsView } from "./ui/ProjectBuildsView";

const P = (extra: Partial<CompilePlacement>): CompilePlacement => ({
  state: "shared",
  runner_name: null,
  runner_owner: null,
  fallback: null,
  wait_s: null,
  ...extra,
});

describe("где идёт сборка: тексты", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it.each([
    [
      P({
        state: "waiting_personal",
        runner_name: "X",
        runner_owner: "me",
        wait_s: 5,
      }),
      "me",
      "Ждём ваш раннер «X»… (до 5 с)",
    ],
    [
      P({ state: "waiting_personal", runner_name: "X", runner_owner: "owner" }),
      "owner",
      "Ждём раннер владельца «X»…",
    ],
    [
      P({ state: "personal", runner_name: "X", runner_owner: "me" }),
      "me",
      "На вашем раннере «X»",
    ],
    [
      P({ state: "personal", runner_name: "X", runner_owner: "owner" }),
      "owner",
      "На раннере владельца «X»",
    ],
    [P({}), "me", "На общем раннере"],
    [
      P({ fallback: "offline" }),
      "me",
      "Ваш раннер не в сети: собрали на общем",
    ],
    [P({ fallback: "busy" }), "me", "Ваш раннер занят: собрали на общем"],
    [
      P({ fallback: "timeout", wait_s: 5 }),
      "me",
      "Ваш раннер не взял сборку за 5 с: собрали на общем",
    ],
    [
      P({ fallback: "lost" }),
      "me",
      "Ваш раннер пропал посреди сборки: повторили на общем",
    ],
    [
      P({ fallback: "disabled" }),
      "me",
      "Личные раннеры выключены: собрали на общем",
    ],
    [
      P({ fallback: "offline" }),
      "owner",
      "Раннер владельца не в сети: собрали на общем",
    ],
  ] as const)("%o для %s", (placement, perspective, text) => {
    render(
      <BuildPlacementChip placement={placement} perspective={perspective} />,
    );
    const el = screen.getByTestId("build-placement");
    expect(el).toHaveTextContent(text);
    expect(el).toHaveAttribute("data-state", placement.state);
  });

  it("сторона берётся у сервера, если он её прислал", () => {
    expect(
      placementView(
        P({ state: "personal", runner_name: "X", runner_owner: "owner" }),
        "me",
      ).key,
    ).toBe("personalOwner");
  });

  it("ожидание личного раннера: своя плашка", () => {
    render(
      <CompileWaitNotice
        wait={{
          reason: "personal_runner",
          queue_position: null,
          wait_hint_seconds: 5,
          attempt: null,
          max_attempts: null,
        }}
      />,
    );
    expect(
      screen.getByTestId("compile-wait-personal_runner"),
    ).toHaveTextContent("Ждём личный раннер");
  });
});

const INFO: ProjectBuildRunners = {
  policy: "shared",
  editable: true,
  project_kind: "personal",
  personal_runners_enabled: true,
  my_builds: "personal_first",
  wait_s: 5,
  owner_runners: [{ name: "MacBook Анны", state: "online" }],
};

const mount = (info: Partial<ProjectBuildRunners>, onChange = vi.fn()) =>
  render(
    <MemoryRouter>
      <ProjectBuildsView
        status="ready"
        info={{ ...INFO, ...info }}
        onChange={onChange}
      />
    </MemoryRouter>,
  );

describe("настройки проекта: сборки", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("владелец выбирает политику и видит правило своих сборок", async () => {
    const onChange = vi.fn();
    mount({}, onChange);
    expect(screen.getByTestId("project-builds-own")).toHaveTextContent(
      "за 5 с",
    );
    await userEvent.click(screen.getByTestId("project-builds-policy-owner"));
    expect(onChange).toHaveBeenCalledWith("owner");
    expect(
      screen.getByTestId("project-builds-owner-runners"),
    ).toHaveTextContent("MacBook Анны");
  });

  it("два раннера с одним именем: оба видны, без повторных ключей", () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mount({
      owner_runners: [
        { name: "MacBook", state: "online" },
        { name: "MacBook", state: "offline" },
      ],
    });
    expect(
      screen.getByTestId("project-builds-owner-runners").querySelectorAll("li"),
    ).toHaveLength(2);
    expect(error).not.toHaveBeenCalled();
    error.mockRestore();
  });

  it("без своих раннеров ведёт к подключению", () => {
    mount({ owner_runners: [] });
    expect(screen.getByTestId("project-builds-connect")).toHaveAttribute(
      "href",
      "/settings/runners",
    );
  });

  it("соавтор видит только чтение", () => {
    mount({ editable: false, policy: "owner" });
    expect(screen.queryByTestId("project-builds-policy-owner")).toBeNull();
    expect(screen.getByTestId("project-builds-readonly")).toHaveTextContent(
      "Сборки идут на раннере владельца «MacBook Анны», когда он в сети; иначе на общих.",
    );
  });

  it("проект организации и выключенные личные раннеры", () => {
    mount({ project_kind: "org", editable: false });
    expect(screen.getByTestId("project-builds-org")).toBeInTheDocument();
    cleanup();
    mount({ personal_runners_enabled: false });
    expect(screen.getByTestId("project-builds-disabled")).toBeInTheDocument();
    expect(
      screen.getByTestId("project-builds-policy-owner").querySelector("input"),
    ).toBeDisabled();
  });
});
