import { act, cleanup, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import {
  SR_DOC,
  SR_PROJECT_ID,
  SR_REVIEW_DOC,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import { makeGuardHarness } from "@entities/signing-route/testing/guard";

const mutate = vi.fn();
const mutateAsync = vi.fn();

vi.mock("@entities/project", () => ({
  useUpdateProject: () => ({ mutate, mutateAsync }),
}));

import { useProjectAutosave } from "./useProjectAutosave";

// Поля проекта (signing-route.md, 12.7): один вопрос на проект с перечнем документов.

const project = {
  id: SR_PROJECT_ID,
  name: "Курсовая",
  meta: { topic: "Старая тема" },
} as unknown as Parameters<typeof useProjectAutosave>[0];

const renderAutosave = () => {
  const harness = makeGuardHarness({
    routes: [
      makeSigningRouteSummary({ docs: [SR_DOC.doc_id, SR_REVIEW_DOC.doc_id] }),
    ],
  });
  return renderHook(() => useProjectAutosave(project), {
    wrapper: harness.wrapper,
  });
};

describe("useProjectAutosave and the signing guard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    mutate.mockReset();
    mutateAsync.mockReset().mockResolvedValue(undefined);
  });
  afterEach(cleanup);

  it("asks once with the list of documents before the first field change", async () => {
    const user = userEvent.setup();
    const { result } = renderAutosave();

    act(() => {
      result.current.saveNow({ meta: { topic: "Новая тема" } });
    });
    expect(
      await screen.findByRole("dialog", { name: "Документы на подписании" }),
    ).toHaveTextContent(
      "Документы на подписании: Заявление о выборе темы, Отзыв руководителя. Изменения не попадут в подписываемые версии. Продолжить?",
    );
    // Поле не поменялось, пока нет ответа.
    expect(result.current.effective.meta).toEqual({ topic: "Старая тема" });
    expect(mutate).not.toHaveBeenCalled();

    // Правка, сделанная до ответа, не теряется и идёт следом.
    act(() => {
      result.current.saveNow({ authors: [] });
    });
    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(mutate).toHaveBeenCalledTimes(2);
    expect(mutate.mock.calls[1]?.[0]).toEqual({
      id: SR_PROJECT_ID,
      data: { meta: { topic: "Новая тема" }, authors: [] },
    });

    // Дальше без вопросов.
    act(() => {
      result.current.saveNow({ supervisor: null });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutate).toHaveBeenCalledTimes(3);
  });

  it("cancel keeps the fields as they were", async () => {
    const user = userEvent.setup();
    const { result } = renderAutosave();
    act(() => {
      result.current.patch({ meta: { topic: "Новая тема" } });
    });
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    expect(result.current.effective.meta).toEqual({ topic: "Старая тема" });
    expect(mutate).not.toHaveBeenCalled();
  });

  it("does not ask for fields documents are not built from", () => {
    const { result } = renderAutosave();
    act(() => {
      result.current.saveNow({ name: "Новое имя", pinned: true });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutate).toHaveBeenCalledTimes(1);
  });
});
