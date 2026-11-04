import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import {
  makeLink,
  makePeople,
  makePerson,
  makeServer,
} from "@entities/connected-device/testing";
import type { PersonOnline } from "@entities/connected-device";
import { PeopleOnline } from "./ui/PeopleOnline";
import { ProjectPeople } from "./ui/ProjectPeople";

const api = vi.hoisted(() => ({
  signal: vi.fn(),
  leave: vi.fn(),
  link: vi.fn(),
  mode: { value: "server" },
}));

vi.mock("@entities/connected-device/api/peopleApi", () => ({
  peopleApi: { signal: api.signal, leave: api.leave },
}));
vi.mock("@entities/connected-device/api/deviceApi", () => ({
  deviceApi: { project: vi.fn(), account: vi.fn(), forget: vi.fn() },
  studioLinkApi: { link: api.link, device: vi.fn(), rename: vi.fn() },
}));
vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useBootstrap: () => ({ data: { mode: api.mode.value } }),
}));
vi.mock("@entities/document", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/document")),
  useDocuments: () => ({
    data: [{ id: "tz", name: { ru: "Техническое задание", en: "Spec" } }],
  }),
}));

const Where = () => <span data-testid="where">{useLocation().pathname}</span>;

const renderPeople = (node: React.ReactNode) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/projects/p1/documents/a"]}>
        {node}
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const me = makePerson({ user_id: "me", name: "Анна Петрова", me: true });
const boris = makePerson({
  user_id: "boris",
  name: "Борис Смирнов",
  initials: "БС",
  color: "#2f9e44",
  role: "editor",
  activity: "editing",
  doc_id: "tz",
});
const local = makePerson({
  user_id: "gleb",
  name: "Глеб Орлов",
  initials: "ГО",
  role: "editor",
  activity: "local",
  channels: ["studio"],
});

const docName = (id: string) => (id === "tz" ? "Техническое задание" : null);

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  api.mode.value = "server";
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("аватары людей в проекте", () => {
  it("один только сам смотрящий: ничего не рисуется", () => {
    renderPeople(<PeopleOnline people={makePeople([me])} docName={docName} />);
    expect(screen.queryByTestId("project-people")).toBeNull();
  });

  it("у аватара полная подпись: имя, роль, место, устройство", () => {
    renderPeople(
      <PeopleOnline
        people={makePeople([me, boris, local])}
        docName={docName}
        onOpenDoc={vi.fn()}
      />,
    );
    const group = screen.getByRole("group", { name: /3 человека/ });
    const avatars = within(group).getAllByTestId("person-avatar");
    expect(avatars).toHaveLength(3);
    expect(avatars[0]).toHaveAttribute("data-me", "true");
    expect(avatars[0]).toHaveAccessibleName(/Анна Петрова \(вы\)/);
    expect(avatars[1]).toHaveAccessibleName(
      "Борис Смирнов, Редактор, редактирует «Техническое задание», в браузере, в сети. Перейти к документу",
    );
    expect(avatars[2]).toHaveAccessibleName(
      "Глеб Орлов, Редактор, работает локально, в локальной Студии, в сети",
    );
  });

  it("цвет аватара тот, что прислал сервер (он же у курсора)", () => {
    renderPeople(
      <PeopleOnline people={makePeople([me, boris])} docName={docName} />,
    );
    const [, second] = screen.getAllByTestId("person-avatar");
    expect(second?.style.backgroundColor).toBe("rgb(47, 158, 68)");
  });

  it("пять аватаров и «+3», остальные в списке по нажатию", async () => {
    const many: PersonOnline[] = [
      me,
      ...Array.from({ length: 7 }, (_, i) =>
        makePerson({
          user_id: `x${String(i)}`,
          name: `Человек ${String(i)}`,
          initials: "Ч",
        }),
      ),
    ];
    renderPeople(<PeopleOnline people={makePeople(many)} docName={docName} />);
    expect(screen.getAllByTestId("person-avatar")).toHaveLength(5);
    const more = screen.getByTestId("people-more");
    expect(more).toHaveTextContent("+3");
    await userEvent.click(more);
    expect(screen.getAllByTestId("people-row")).toHaveLength(8);
  });

  it("нажатие на аватар ведёт к документу человека", async () => {
    const open = vi.fn();
    renderPeople(
      <PeopleOnline
        people={makePeople([me, boris])}
        docName={docName}
        onOpenDoc={open}
      />,
    );
    await userEvent.click(screen.getAllByTestId("person-avatar")[1]!);
    expect(open).toHaveBeenCalledWith(boris);
  });

  it("свой аватар и работающий локально никуда не ведут, а открывают список", async () => {
    const open = vi.fn();
    renderPeople(
      <PeopleOnline
        people={makePeople([me, local])}
        docName={docName}
        onOpenDoc={open}
      />,
    );
    await userEvent.click(screen.getAllByTestId("person-avatar")[1]!);
    expect(open).not.toHaveBeenCalled();
    expect(screen.getByTestId("people-list")).toBeInTheDocument();
  });

  it("документ, которого смотрящий не видит, не называется и не открывается", () => {
    const hidden = makePerson({
      user_id: "z",
      name: "Зоя",
      activity: "editing",
      doc_id: "secret",
    });
    renderPeople(
      <PeopleOnline
        people={makePeople([me, hidden])}
        docName={docName}
        onOpenDoc={vi.fn()}
      />,
    );
    const avatar = screen.getAllByTestId("person-avatar")[1]!;
    expect(avatar).toHaveAccessibleName(
      /Зоя, Владелец, редактирует, в браузере/,
    );
    expect(avatar.getAttribute("aria-label")).not.toContain("secret");
    expect(avatar.getAttribute("aria-label")).not.toContain("Перейти");
  });

  it("список работает с клавиатуры: строка с документом кнопка, Enter переходит", async () => {
    const open = vi.fn();
    renderPeople(
      <PeopleOnline
        people={makePeople([me, boris, local])}
        docName={docName}
        onOpenDoc={open}
      />,
    );
    const user = userEvent.setup();
    screen.getByTestId("people-more").focus();
    await user.keyboard("{Enter}");
    const list = screen.getByTestId("people-list");
    const buttons = within(list).getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveTextContent("Борис Смирнов");
    expect(buttons[0]).toHaveTextContent("редактирует «Техническое задание»");
    buttons[0]!.focus();
    await user.keyboard("{Enter}");
    expect(open).toHaveBeenCalledWith(boris);
    expect(screen.queryByTestId("people-list")).toBeNull();
  });

  it("список называет себя и уточняет, что показано", async () => {
    renderPeople(
      <PeopleOnline people={makePeople([me, boris])} docName={docName} />,
    );
    await userEvent.click(screen.getByTestId("people-more"));
    const rows = screen.getAllByTestId("people-row");
    expect(rows[0]).toHaveTextContent("Анна Петрова (вы)");
    expect(screen.getByTestId("people-list")).toHaveTextContent(
      "без содержимого",
    );
  });

  it("на английском: «is editing», роль и устройство", async () => {
    await i18n.changeLanguage("en");
    renderPeople(
      <PeopleOnline people={makePeople([me, boris])} docName={docName} />,
    );
    expect(screen.getAllByTestId("person-avatar")[1]).toHaveAccessibleName(
      /Борис Смирнов, Editor, is editing “Техническое задание”, in the browser, online/,
    );
  });
});

describe("люди в шапке: облако и локальная Студия", () => {
  it("облако: сигнал вкладки уходит с местом, в ответе люди", async () => {
    api.signal.mockResolvedValue(makePeople([me, boris]));
    renderPeople(<ProjectPeople projectId="p1" docId="a" />);
    expect(await screen.findByTestId("project-people")).toBeInTheDocument();
    expect(api.signal).toHaveBeenCalledTimes(1);
    expect(api.signal).toHaveBeenCalledWith("p1", {
      session_id: expect.stringMatching(/^[A-Za-z0-9_-]{8,64}$/) as string,
      activity: "viewing",
      doc_id: "a",
    });
  });

  it("вне документа вкладка сообщает «в проекте» без документа", async () => {
    api.signal.mockResolvedValue(makePeople([me, boris]));
    renderPeople(<ProjectPeople projectId="p1" docId={null} />);
    await screen.findByTestId("project-people");
    expect(api.signal).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ activity: "browsing", doc_id: null }),
    );
  });

  it("уход со страницы убирает сессию сразу", async () => {
    api.signal.mockResolvedValue(makePeople([me, boris]));
    const view = renderPeople(<ProjectPeople projectId="p1" docId="a" />);
    await screen.findByTestId("project-people");
    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });
    expect(api.leave).toHaveBeenCalledWith("p1", expect.any(String));
    view.unmount();
  });

  it("клик по человеку с документом открывает этот документ", async () => {
    api.signal.mockResolvedValue(makePeople([me, boris]));
    renderPeople(<ProjectPeople projectId="p1" docId="a" />);
    await screen.findByTestId("project-people");
    await userEvent.click(screen.getAllByTestId("person-avatar")[1]!);
    expect(screen.getByTestId("where")).toHaveTextContent(
      "/projects/p1/documents/tz",
    );
  });

  it("локальная Студия: люди из ответа облака, своих сигналов нет", async () => {
    api.mode.value = "local";
    api.link.mockResolvedValue(
      makeLink({
        servers: [
          makeServer({
            cloud: {
              online_window_s: 180,
              device: null,
              others: [],
              people: makePeople([me, boris, local]),
            },
          }),
        ],
      }),
    );
    renderPeople(<ProjectPeople projectId="p1" docId={null} />);
    expect(await screen.findByTestId("project-people")).toHaveAttribute(
      "data-count",
      "3",
    );
    expect(api.signal).not.toHaveBeenCalled();
  });

  it("локальная Студия без входа на сервер: ничего", async () => {
    api.mode.value = "local";
    api.link.mockResolvedValue(makeLink({ servers: [] }));
    renderPeople(<ProjectPeople projectId="p1" docId={null} />);
    await vi.waitFor(() => {
      expect(api.link).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("project-people")).toBeNull();
  });
});

describe("стили", () => {
  const css = readFileSync("src/index.css", "utf8");
  const rule = (selector: string): string => {
    const start = css.indexOf(`\n  ${selector} {`);
    expect(start, `правило ${selector}`).toBeGreaterThan(-1);
    return css.slice(start, css.indexOf("}", start));
  };

  it.each([".pp-avatar", ".pp-more", ".pp-row"])(
    "у кнопки %s цвет текста задан явно: в тёмной теме без него текст чёрный",
    (selector) => {
      expect(rule(selector)).toMatch(/\n\s+color:/);
    },
  );
});
