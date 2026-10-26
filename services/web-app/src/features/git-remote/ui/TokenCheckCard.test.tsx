import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib/i18n";
import type { TokenVerdict } from "../model/tokenVerdict";
import { TokenCheckCard } from "./TokenCheckCard";

const info = (over: Partial<NonNullable<TokenVerdict["info"]>> = {}) => ({
  login: "anna.petrova",
  scopes: ["read_repository", "write_repository"],
  expires_at: null,
  sufficiency: "sufficient",
  missing: [],
  ...over,
});

const show = (
  verdict: TokenVerdict | null,
  props: Partial<React.ComponentProps<typeof TokenCheckCard>> = {},
) => render(<TokenCheckCard verdict={verdict} provider="gitlab" {...props} />);

describe("TokenCheckCard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("пока проверка идёт, показывает ожидание", () => {
    show(null);
    expect(screen.getByTestId("token-check-running")).toHaveTextContent(
      "Проверяем токен",
    );
  });

  it("токен подходит: владелец, права и срок", () => {
    const at = new Date(Date.now() + 40 * 24 * 3600 * 1000).toISOString();
    show(
      { kind: "sufficient", info: info({ expires_at: at }) },
      { version: "17.3.1" },
    );
    const card = screen.getByTestId("token-check-sufficient");
    expect(card).toHaveTextContent("Токен подходит");
    const facts = screen.getByTestId("token-facts");
    expect(facts).toHaveTextContent("anna.petrova");
    expect(facts).toHaveTextContent("read_repository");
    expect(facts).toHaveTextContent("write_repository");
    expect(facts).toHaveTextContent("осталось 40 дней");
    expect(facts).toHaveTextContent("GitLab 17.3");
    expect(
      screen.queryByRole("button", { name: "Проверить ещё раз" }),
    ).toBeNull();
  });

  it("мало прав: называет, что добавить, и даёт ссылку на новый токен", () => {
    show(
      {
        kind: "too_narrow",
        info: info({
          scopes: ["read_repository"],
          sufficiency: "too_narrow",
          missing: ["write_repository"],
        }),
      },
      {
        createUrl:
          "https://gitlab.com/-/user_settings/personal_access_tokens?x=1",
      },
    );
    expect(screen.getByTestId("token-check-too_narrow")).toHaveTextContent(
      "Добавь права: write_repository",
    );
    expect(
      screen.getByRole("link", { name: /Создать новый токен/ }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining("personal_access_tokens"),
    );
    expect(
      screen.getByText(/Нужно: read_repository и write_repository/),
    ).toBeInTheDocument();
  });

  it("слишком широкий: называет лишнее право", () => {
    show({
      kind: "too_broad",
      info: info({ scopes: ["api"], sufficiency: "too_broad" }),
    });
    expect(screen.getByTestId("token-check-too_broad")).toHaveTextContent(
      "Лишние права: api",
    );
  });

  it("права не прочитать: спокойное пояснение вместо ошибки", () => {
    show({
      kind: "unknown",
      info: info({ scopes: [], sufficiency: "unknown" }),
    });
    const card = screen.getByTestId("token-check-unknown");
    expect(card).toHaveAttribute("data-tone", "info");
    expect(card).toHaveTextContent("Права проверить не удалось");
  });

  it("просрочен: дата в прошлом и ссылка на новый токен", () => {
    show(
      {
        kind: "expired",
        info: info({
          scopes: [],
          sufficiency: "unknown",
          expires_at: "2026-10-01T00:00:00Z",
        }),
      },
      { createUrl: "https://gitlab.com/x" },
    );
    const card = screen.getByTestId("token-check-expired");
    expect(card).toHaveTextContent("Срок токена истёк");
    expect(screen.getByTestId("token-facts")).toHaveTextContent("истёк");
    expect(
      screen.getByRole("link", { name: /Создать новый токен/ }),
    ).toBeInTheDocument();
  });

  it("отказ сервера и повтор проверки", async () => {
    const onRetry = vi.fn();
    show(
      {
        kind: "error",
        code: "auth_failed",
        detail: "d",
        certificate: null,
        info: null,
      },
      { onRetry },
    );
    expect(screen.getByTestId("token-check-auth_failed")).toHaveTextContent(
      "Сервер не принял токен",
    );
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Проверить ещё раз" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("неизвестный код берёт общий заголовок и текст ошибки", () => {
    show({
      kind: "error",
      code: "git_error",
      detail: "boom",
      certificate: null,
      info: null,
    });
    expect(screen.getByTestId("token-check-git_error")).toHaveTextContent(
      "Не удалось проверить токен",
    );
  });

  it("сертификат: кнопка открывает окно, а не просит повторить", async () => {
    const onReview = vi.fn();
    show(
      {
        kind: "error",
        code: "tls_untrusted_ca",
        detail: "d",
        certificate: null,
        info: null,
      },
      { onReviewCertificate: onReview },
    );
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Проверить сертификат" }));
    expect(onReview).toHaveBeenCalled();
  });

  it("английский язык", async () => {
    await i18n.changeLanguage("en");
    show({ kind: "sufficient", info: info() });
    expect(screen.getByTestId("token-check-sufficient")).toHaveTextContent(
      "The token fits",
    );
  });
});
