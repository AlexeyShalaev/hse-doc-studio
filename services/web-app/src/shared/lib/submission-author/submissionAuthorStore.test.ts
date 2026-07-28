import { beforeEach, describe, expect, it } from "vitest";

import {
  resolveSelectedAuthorSlug,
  useSubmissionAuthorStore,
} from "./submissionAuthorStore";

describe("resolveSelectedAuthorSlug", () => {
  it("keeps a stored slug that is still a managed author", () => {
    expect(resolveSelectedAuthorSlug("ivanov", ["shalaev", "ivanov"])).toBe(
      "ivanov",
    );
  });

  it("falls back to the first author when the stored slug is gone", () => {
    // Состав команды правится в настройках проекта: исчезнувший автор не должен
    // оставлять экран упаковки без цели — иначе пакет собрать нечем.
    expect(resolveSelectedAuthorSlug("petrov", ["shalaev", "ivanov"])).toBe(
      "shalaev",
    );
  });

  it("falls back to the first author when nothing is stored", () => {
    expect(resolveSelectedAuthorSlug(null, ["shalaev", "ivanov"])).toBe(
      "shalaev",
    );
    expect(resolveSelectedAuthorSlug(undefined, ["shalaev"])).toBe("shalaev");
  });

  it("returns null when there is nobody to pick", () => {
    expect(resolveSelectedAuthorSlug("shalaev", [])).toBeNull();
  });
});

describe("useSubmissionAuthorStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useSubmissionAuthorStore.setState({ selectedAuthorBy: {} });
  });

  it("shares one selection per project and persists it", () => {
    useSubmissionAuthorStore.getState().setSelectedAuthor("p1", "ivanov");

    expect(useSubmissionAuthorStore.getState().selectedAuthorBy).toEqual({
      p1: "ivanov",
    });
    // Ключ унаследован от рейки «Сдача»: сохранённые выборы переживают переезд.
    expect(window.localStorage.getItem("hse-studio.nav.author.p1")).toBe(
      "ivanov",
    );
  });

  it("keeps projects independent", () => {
    const { setSelectedAuthor } = useSubmissionAuthorStore.getState();
    setSelectedAuthor("p1", "ivanov");
    setSelectedAuthor("p2", "shalaev");

    expect(useSubmissionAuthorStore.getState().selectedAuthorBy).toEqual({
      p1: "ivanov",
      p2: "shalaev",
    });
  });

  it("clears the selection and the stored key on null", () => {
    const { setSelectedAuthor } = useSubmissionAuthorStore.getState();
    setSelectedAuthor("p1", "ivanov");
    setSelectedAuthor("p1", null);

    expect(useSubmissionAuthorStore.getState().selectedAuthorBy).toEqual({});
    expect(window.localStorage.getItem("hse-studio.nav.author.p1")).toBeNull();
  });
});
