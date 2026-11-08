import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NOW, minutesBefore } from "@entities/connected-device/testing";
import type {
  DocumentBuildStatus,
  LocalBuilds,
  ProjectBuilds,
} from "@entities/project-build";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { fetchErrorCode, fetchResultText } from "./model/useFetchBuild";
import { DocBuildNote, DocBuildNoteView } from "./ui/DocBuildNote";
import { DocBuildLine } from "./ui/DocBuildLine";
import { FetchAllNotice } from "./ui/FetchAllNotice";
import { describeCloudDoc, describeLocalDoc } from "@entities/project-build";

const api = vi.hoisted(() => ({
  cloud: vi.fn(),
  local: vi.fn(),
  fetch: vi.fn(),
  mode: { value: "local" },
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@entities/project-build/api/buildApi", () => ({
  cloudBuildsApi: { list: api.cloud },
  localBuildsApi: { list: api.local, fetch: api.fetch },
}));

vi.mock("@shared/lib", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/lib")),
  toast: api.toast,
}));

vi.mock("@entities/session", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@entities/session")),
  useBootstrap: () => ({ data: { mode: api.mode.value } }),
}));

const cloudBuild = (over: Record<string, unknown> = {}) => ({
  at: minutesBefore(5),
  commit: "9f2c1e7a4b0d",
  pages: 14,
  fresh: true,
  sha256: "a".repeat(64),
  size: 1000,
  ...over,
});

const status = (
  over: Partial<DocumentBuildStatus> = {},
): DocumentBuildStatus => ({
  doc_id: "tz",
  local: null,
  cloud: cloudBuild(),
  cloud_running: false,
  studio: null,
  relation: "cloud_only",
  can_fetch: true,
  ...over,
});

const localBuilds = (docs: DocumentBuildStatus[]): LocalBuilds => ({
  connected: true,
  cloud_error: null,
  local_head: "9f2c1e7a4b0d",
  local_dirty: false,
  cloud_head: "9f2c1e7a4b0d",
  documents: docs,
});

const wrap = (node: React.ReactNode) =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {node}
    </QueryClientProvider>,
  );

beforeEach(() => {
  vi.setSystemTime(NOW);
  api.mode.value = "local";
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("строка сборки документа", () => {
  it("локально: «собрано в облаке 5 минут назад, у вас нет этой сборки»", () => {
    render(
      <DocBuildLine view={describeLocalDoc(status())} now={NOW} docId="tz" />,
    );
    const line = screen.getByTestId("doc-build-tz");
    expect(line).toHaveTextContent("в облаке 5 мин, у вас нет");
    expect(line).toHaveAttribute(
      "title",
      expect.stringContaining(
        "Собрано в облаке 5 минут назад, у вас нет этой сборки",
      ),
    );
    expect(line).toHaveTextContent("актуальна");
    expect(line).toHaveAttribute("data-fresh", "true");
  });

  it("облако: «собрано в Студии, в облаке нет» и устаревшая версия", () => {
    render(
      <DocBuildLine
        view={describeCloudDoc({
          doc_id: "vkr",
          cloud: null,
          cloud_running: false,
          cloud_failed_at: null,
          studio: {
            ...cloudBuild({ fresh: false }),
            artifact_id: "a",
            by_name: "Анна",
          },
        })}
        now={NOW}
        docId="vkr"
      />,
    );
    const line = screen.getByTestId("doc-build-vkr");
    expect(line).toHaveTextContent("Студия 5 мин, в облаке нет");
    expect(line).toHaveAttribute(
      "title",
      expect.stringContaining("собрано в Студии 5 минут назад, в облаке нет"),
    );
    expect(line).toHaveTextContent("устарела: проект изменился");
  });
});

describe("полоса в панели сборки", () => {
  it("кнопка «Получить сборку» зовёт получение; «Всё равно заменить» только когда локальная новее", async () => {
    const onFetch = vi.fn();
    const { rerender } = render(
      <DocBuildNoteView
        view={describeLocalDoc(status())}
        now={NOW}
        pending={false}
        onFetch={onFetch}
      />,
    );
    await userEvent.click(screen.getByTestId("doc-build-fetch"));
    expect(onFetch).toHaveBeenCalledWith(false);
    expect(screen.queryByTestId("doc-build-force")).toBeNull();
    rerender(
      <DocBuildNoteView
        view={describeLocalDoc(
          status({
            relation: "local_newer",
            can_fetch: false,
            local: {
              at: minutesBefore(1),
              commit: "x",
              fresh: true,
              sha256: "b",
              pages: 1,
              from_cloud: false,
            },
          }),
        )}
        now={NOW}
        pending={false}
        onFetch={onFetch}
      />,
    );
    expect(screen.queryByTestId("doc-build-fetch")).toBeNull();
    await userEvent.click(screen.getByTestId("doc-build-force"));
    expect(onFetch).toHaveBeenLastCalledWith(true);
  });

  it("локальная Студия: загрузка по кнопке уходит в API без auto", async () => {
    api.local.mockResolvedValue(localBuilds([status()]));
    api.fetch.mockResolvedValue({
      items: [{ doc_id: "tz", status: "downloaded", code: null, size: 1 }],
    });
    wrap(<DocBuildNote projectId="p1" docId="tz" />);
    await userEvent.click(await screen.findByTestId("doc-build-fetch"));
    await waitFor(() => {
      expect(api.fetch).toHaveBeenCalledWith("p1", {
        doc_id: "tz",
        force: false,
        auto: false,
      });
    });
  });

  it("облако: полоса без кнопки получения", async () => {
    api.mode.value = "server";
    const builds: ProjectBuilds = {
      head: "9f2c1e7a4b0d",
      dirty: false,
      max_pdf_bytes: 1,
      documents: [
        {
          doc_id: "tz",
          cloud: cloudBuild(),
          cloud_running: false,
          cloud_failed_at: null,
          studio: null,
        },
      ],
    };
    api.cloud.mockResolvedValue(builds);
    wrap(<DocBuildNote projectId="p1" docId="tz" />);
    expect(await screen.findByTestId("doc-build-note")).toHaveTextContent(
      "собрано в облаке 5 минут назад",
    );
    expect(screen.queryByTestId("doc-build-fetch")).toBeNull();
    expect(api.local).not.toHaveBeenCalled();
  });

  it("проект не подключён к облаку: полосы нет", async () => {
    api.local.mockResolvedValue({ ...localBuilds([]), connected: false });
    wrap(<DocBuildNote projectId="p1" docId="tz" />);
    await waitFor(() => {
      expect(api.local).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("doc-build-note")).toBeNull();
  });
});

describe("получить все облачные сборки", () => {
  it("плашка над списком с числом сборок и одной кнопкой", async () => {
    api.local.mockResolvedValue(
      localBuilds([status(), status({ doc_id: "vkr" })]),
    );
    api.fetch.mockResolvedValue({ items: [] });
    wrap(<FetchAllNotice projectId="p1" />);
    expect(await screen.findByTestId("fetch-all-notice")).toHaveTextContent(
      "В облаке есть 2 сборки, которых нет у вас",
    );
    await userEvent.click(screen.getByTestId("fetch-all-builds"));
    await waitFor(() => {
      expect(api.fetch).toHaveBeenCalledWith("p1", {
        doc_id: null,
        force: false,
        auto: false,
      });
    });
  });

  it("всё получено: плашки нет", async () => {
    api.local.mockResolvedValue(
      localBuilds([status({ relation: "same", can_fetch: false })]),
    );
    wrap(<FetchAllNotice projectId="p1" />);
    await waitFor(() => {
      expect(api.local).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("fetch-all-notice")).toBeNull();
  });
});

describe("документ выпускается не в PDF", () => {
  const slides = (over: Partial<DocumentBuildStatus> = {}) =>
    status({
      doc_id: "presentation",
      can_fetch: false,
      fetch_blocked: "not_pdf",
      ...over,
    });

  it("не входит в число облачных сборок и в «Получить облачные сборки»", async () => {
    api.local.mockResolvedValue(localBuilds([status(), slides()]));
    wrap(<FetchAllNotice projectId="p1" />);
    expect(await screen.findByTestId("fetch-all-notice")).toHaveTextContent(
      "В облаке есть 1 сборка, которой нет у вас",
    );
  });

  it("единственный такой документ: плашки нет", async () => {
    api.local.mockResolvedValue(localBuilds([slides()]));
    wrap(<FetchAllNotice projectId="p1" />);
    await waitFor(() => {
      expect(api.local).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("fetch-all-notice")).toBeNull();
  });

  it("полоса без кнопки получения и с объяснением", () => {
    render(
      <DocBuildNoteView
        view={describeLocalDoc(slides())}
        now={NOW}
        pending={false}
        onFetch={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("doc-build-fetch")).toBeNull();
    expect(screen.getByTestId("doc-build-blocked")).toHaveTextContent(
      "Документ выпускается не в PDF, облачную сборку получить нельзя: соберите его у себя.",
    );
  });

  it("старая Студия без поля: объяснения нет", () => {
    const { fetch_blocked: _omit, ...legacy } = status();
    expect(describeLocalDoc(legacy).fetchBlocked).toBeNull();
  });
});

describe("тексты итога получения", () => {
  const t = i18n.getFixedT("ru", "devices");

  it.each([
    [
      "not_pdf",
      "not_pdf",
      "Этот документ выпускается не в PDF, его облачную сборку получить нельзя. Соберите его у себя.",
    ],
    [
      "failed",
      "git_server_unreachable",
      "Не удалось получить сборку: сервер Студии не ответил. Проверьте подключение к сети.",
    ],
    [
      "failed",
      "cloud_pdf_forbidden",
      "Нет права читать исходники и результат этого проекта в облаке, сборку получить нельзя.",
    ],
    [
      "failed",
      "auth_failed",
      "Сервер Студии не принял вход этой Студии. Войдите на сервер заново и повторите.",
    ],
    [
      "failed",
      "cloud_pdf_checksum_mismatch",
      "Файл сборки пришёл повреждённым и не был сохранён. Попробуйте ещё раз.",
    ],
    [
      "failed",
      "cloud_pdf_write_failed",
      "Не удалось записать PDF на диск. Закройте его в других программах и проверьте свободное место.",
    ],
    [
      "failed",
      "output_path_invalid",
      "Путь результата документа выходит за папку проекта, сборку не записали.",
    ],
    [
      "failed",
      "secrets_unavailable",
      "Хранилище секретов недоступно, сохранённые токены не читаются.",
    ],
    ["failed", "something_new", "Не удалось получить сборку."],
    ["failed", null, "Не удалось получить сборку."],
  ] as const)("%s / %s", (status, code, text) => {
    expect(fetchResultText(t, status, code)).toBe(text);
  });

  it("о связи говорит только сетевой сбой и молчание сервера", () => {
    const codes = [
      "not_pdf",
      "cloud_pdf_forbidden",
      "auth_failed",
      "cloud_pdf_checksum_mismatch",
      "cloud_pdf_write_failed",
      "output_path_invalid",
      "output_unknown",
      "something_new",
    ];
    for (const code of codes) {
      expect(fetchResultText(t, "failed", code)).not.toMatch(/связ/);
    }
    expect(fetchResultText(t, "failed", "network")).toMatch(/связи/);
  });

  it("английские тексты на месте", () => {
    const en = i18n.getFixedT("en", "devices");
    expect(fetchResultText(en, "not_pdf", "not_pdf")).toBe(
      "This document is not produced as a PDF, so its cloud build cannot be fetched. Build it here.",
    );
    expect(fetchResultText(en, "failed", "cloud_pdf_write_failed")).toBe(
      "Could not write the PDF to disk. Close it in other programs and check free space.",
    );
  });

  it("код причины из ответа маршрута получения", () => {
    expect(fetchErrorCode(new ApiError("x", "unknown_error", 0))).toBe(
      "network",
    );
    expect(
      fetchErrorCode(
        new ApiError("git_server_unreachable", "unknown_error", 502),
      ),
    ).toBe("git_server_unreachable");
    expect(fetchErrorCode(new ApiError("Сбой", "auth_failed", 409))).toBe(
      "auth_failed",
    );
    expect(
      fetchErrorCode(new ApiError("Проект не подключён", "unknown_error", 404)),
    ).toBeNull();
    expect(fetchErrorCode(new Error("boom"))).toBeNull();
  });

  it("тост по документу pptx: честный текст, а не «проверьте связь»", async () => {
    api.local.mockResolvedValue(localBuilds([status()]));
    api.fetch.mockResolvedValue({
      items: [
        { doc_id: "tz", status: "downloaded", code: null, size: 1 },
        {
          doc_id: "presentation",
          status: "not_pdf",
          code: "not_pdf",
          size: null,
        },
      ],
    });
    wrap(<DocBuildNote projectId="p1" docId="tz" />);
    await userEvent.click(await screen.findByTestId("doc-build-fetch"));
    await waitFor(() => {
      expect(api.toast.error).toHaveBeenCalledWith(
        "Этот документ выпускается не в PDF, его облачную сборку получить нельзя. Соберите его у себя.",
      );
    });
    expect(api.toast.success).toHaveBeenCalledWith(
      "Сборка получена: документ открывается без пересборки.",
    );
  });
});
