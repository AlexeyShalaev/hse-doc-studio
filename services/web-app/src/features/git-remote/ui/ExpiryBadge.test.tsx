import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { ExpiryBadge } from "./ExpiryBadge";

const NOW = Date.parse("2026-10-27T12:00:00Z");
const at = (days: number): string =>
  new Date(NOW + days * 24 * 3600 * 1000).toISOString();

describe("ExpiryBadge", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("ничего не рисует без срока и пока до срока далеко", () => {
    const { container, rerender } = render(
      <ExpiryBadge expiresAt={null} now={NOW} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<ExpiryBadge expiresAt={at(90)} now={NOW} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ExpiryBadge expiresAt={at(90)} now={NOW} showFar />);
    expect(screen.getByTestId("expiry-badge")).toHaveTextContent(
      "Действует до",
    );
  });

  it("скоро: предупреждающая плашка со склонением", () => {
    const { rerender } = render(<ExpiryBadge expiresAt={at(1)} now={NOW} />);
    expect(screen.getByTestId("expiry-badge")).toHaveTextContent(
      "Истекает через 1 день",
    );
    rerender(<ExpiryBadge expiresAt={at(2)} now={NOW} />);
    expect(screen.getByTestId("expiry-badge")).toHaveTextContent("через 2 дня");
    rerender(<ExpiryBadge expiresAt={at(11)} now={NOW} />);
    expect(screen.getByTestId("expiry-badge")).toHaveTextContent(
      "через 11 дней",
    );
    expect(screen.getByTestId("expiry-badge")).toHaveAttribute(
      "data-state",
      "soon",
    );
  });

  it("истёк: плашка ошибки, сегодня и несколько дней назад", () => {
    const { rerender } = render(<ExpiryBadge expiresAt={at(-0.2)} now={NOW} />);
    expect(screen.getByTestId("expiry-badge")).toHaveTextContent(
      "Истёк сегодня",
    );
    rerender(<ExpiryBadge expiresAt={at(-5)} now={NOW} />);
    expect(screen.getByTestId("expiry-badge")).toHaveTextContent(
      "Истёк 5 дней назад",
    );
    expect(screen.getByTestId("expiry-badge")).toHaveAttribute(
      "data-state",
      "expired",
    );
  });

  it("английский язык", async () => {
    await i18n.changeLanguage("en");
    render(<ExpiryBadge expiresAt={at(1)} now={NOW} />);
    expect(screen.getByTestId("expiry-badge")).toHaveTextContent(
      "Expires in 1 day",
    );
  });
});
