import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { VcsCommit } from "@entities/vcs";
import { i18n } from "@shared/lib/i18n";
import { VcsTimeline, type VcsTimelineProps } from "./VcsTimeline";

const commit = (id: string, overrides: Partial<VcsCommit> = {}): VcsCommit => ({
  id,
  short_id: id.slice(0, 7),
  kind: "edit",
  message: `Версия ${id}`,
  author: "Иван Смирнов",
  created_at: "2026-10-26T10:00:00Z",
  parents: [],
  refs: [],
  author_email: "ivan@edu.hse.ru",
  ...overrides,
});

const setup = (commits: VcsCommit[], props: Partial<VcsTimelineProps> = {}) => {
  const onSelect = vi.fn();
  const onRestore = vi.fn();
  render(
    <VcsTimeline
      commits={commits}
      selectedId={null}
      headId={null}
      variant="auto"
      meEmail="ivan@edu.hse.ru"
      onSelect={onSelect}
      onRestore={onRestore}
      {...props}
    />,
  );
  return { onSelect, onRestore };
};

describe("VcsTimeline", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("shows no sync markers and no avatars without a remote and without author e-mails", () => {
    setup([commit("a1", { author_email: null }), commit("a2", { sync: null })]);
    expect(screen.queryAllByTestId("sync-mark")).toHaveLength(0);
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("marks each version as pushed, waiting or received, with an accessible name", () => {
    setup([
      commit("p1", { sync: "pushed" }),
      commit("u1", { sync: "unpushed" }),
      commit("i1", {
        sync: "incoming",
        author: "Анна Петрова",
        author_email: "anna@edu.hse.ru",
      }),
    ]);
    expect(
      screen.getByRole("img", { name: "Уже в репозитории" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Ждёт отправки" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Получено от Анна Петрова" }),
    ).toBeInTheDocument();
  });

  it("gives teammates' versions an initials avatar and a name, but not the user's own", () => {
    setup([
      commit("own", { message: "Моя правка" }),
      commit("other", {
        message: "Чужая правка",
        author: "Анна Петрова",
        author_email: "anna@edu.hse.ru",
      }),
    ]);
    const avatar = screen.getByRole("img", { name: "Анна Петрова" });
    expect(avatar).toHaveTextContent("АП");
    expect(screen.getByText(/· Анна Петрова/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Иван Смирнов" })).toBeNull();
  });

  it("writes merge rows as a merge of N files", () => {
    setup([
      commit("m1", {
        kind: "sync",
        is_merge: true,
        message: "Слияние с репозиторием",
        stats: { files: 3, insertions: 9, deletions: 1 },
      }),
      commit("m2", { kind: "sync", is_merge: true, message: "Пустое слияние" }),
    ]);
    expect(screen.getByText(/Слияние: 3 файла/)).toBeInTheDocument();
    expect(screen.getByText(/· Слияние$/)).toBeInTheDocument();
  });

  it("uses English wording when the interface language is English", async () => {
    await i18n.changeLanguage("en");
    setup([
      commit("u1", { sync: "unpushed" }),
      commit("m1", {
        is_merge: true,
        kind: "sync",
        stats: { files: 1, insertions: 1, deletions: 0 },
      }),
    ]);
    expect(
      screen.getByRole("img", { name: "Waiting to be sent" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Merge: 1 file/)).toBeInTheDocument();
  });

  it("disables restore for a version that exists only in the repository", async () => {
    const user = userEvent.setup();
    const { onRestore } = setup([
      commit("i1", { sync: "incoming", author_email: "anna@edu.hse.ru" }),
      commit("p1", { sync: "pushed" }),
    ]);
    const buttons = screen.getAllByRole("button", { name: /Вернуться/ });
    expect(buttons[0]).toBeDisabled();
    expect(buttons[0]).toHaveAttribute(
      "title",
      expect.stringContaining("Сначала синхронизируй"),
    );
    const [, pushed] = buttons;
    if (!pushed) throw new Error("restore button missing");
    expect(pushed).toBeEnabled();
    await user.click(pushed);
    expect(onRestore).toHaveBeenCalledWith(
      expect.objectContaining({ id: "p1" }),
    );
  });

  it("selects a row by click but does not select it when restore is clicked", async () => {
    const user = userEvent.setup();
    const { onSelect, onRestore } = setup([commit("a1")]);
    await user.click(screen.getByText("Версия a1"));
    expect(onSelect).toHaveBeenCalledWith("a1");
    onSelect.mockClear();
    await user.click(screen.getByRole("button", { name: /Вернуться/ }));
    expect(onRestore).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows the current marker instead of restore for the head", () => {
    setup([commit("a1")], { headId: "a1" });
    expect(screen.getByText("сейчас")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Вернуться/ })).toBeNull();
  });

  it("offers Show more only when the server has more rows and asks for the next page", async () => {
    const user = userEvent.setup();
    const onLoadMore = vi.fn();
    const { rerender } = render(
      <VcsTimeline
        commits={[commit("a1")]}
        selectedId={null}
        headId={null}
        variant="auto"
        onSelect={vi.fn()}
        onRestore={vi.fn()}
        onLoadMore={onLoadMore}
      />,
    );
    expect(screen.queryByRole("button", { name: "Показать ещё" })).toBeNull();
    rerender(
      <VcsTimeline
        commits={[commit("a1")]}
        selectedId={null}
        headId={null}
        variant="auto"
        onSelect={vi.fn()}
        onRestore={vi.fn()}
        hasMore
        onLoadMore={onLoadMore}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
    rerender(
      <VcsTimeline
        commits={[commit("a1")]}
        selectedId={null}
        headId={null}
        variant="auto"
        onSelect={vi.fn()}
        onRestore={vi.fn()}
        hasMore
        isLoadingMore
        onLoadMore={onLoadMore}
      />,
    );
    expect(screen.getByRole("button", { name: /Показать ещё/ })).toBeDisabled();
  });

  it("groups rows by day under sticky headers with a per-day count", () => {
    setup(
      [
        commit("a1", { created_at: "2026-10-26T10:00:00Z" }),
        commit("a2", { created_at: "2026-10-26T09:00:00Z" }),
        commit("a3", { created_at: "2026-10-20T09:00:00Z" }),
      ],
      { groupByDate: true },
    );
    const headers = document.querySelectorAll(".vcs-day-header");
    expect(headers).toHaveLength(2);
    expect(
      within(headers[0] as HTMLElement).getByText("2"),
    ).toBeInTheDocument();
  });

  it("falls back to a generic icon for an unknown kind", () => {
    setup([commit("x1", { kind: "from_the_future" })]);
    expect(screen.getByText("Версия x1")).toBeInTheDocument();
  });
});
