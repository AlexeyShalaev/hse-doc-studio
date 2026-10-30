import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { RunnerPairView, type RunnerPairViewProps } from "./RunnerPairView";

const NOW = Date.parse("2026-10-30T09:42:00Z");
const INFO = {
  user_code: "BCDF-2345",
  name: "MacBook Анны",
  host_kind: "desktop" as const,
  requested_at: "2026-10-30T09:40:00Z",
  expires_at: "2026-10-30T09:50:00Z",
  client_ip: "203.0.113.7",
  status: "pending" as const,
};
const noop = () => undefined;
const mount = (extra: Partial<RunnerPairViewProps>) =>
  render(
    <MemoryRouter>
      <RunnerPairView
        state={{ kind: "enter" }}
        now={NOW}
        onCode={noop}
        onApprove={noop}
        onDeny={noop}
        onOtherCode={noop}
        {...extra}
      />
    </MemoryRouter>,
  );

describe("страница подтверждения сопряжения", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("ждёт решения: устройство, IP, обратный отсчёт и предупреждение", async () => {
    const onApprove = vi.fn();
    mount({ state: { kind: "pending", info: INFO }, onApprove });
    expect(
      screen.getByText("Подключить «MacBook Анны» как ваш раннер?"),
    ).toBeInTheDocument();
    expect(screen.getByText("203.0.113.7")).toBeInTheDocument();
    expect(screen.getByTestId("runner-pair-countdown")).toHaveTextContent(
      "ещё 8:00",
    );
    expect(
      screen.getByText(/Подтверждайте, только если вы сами/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("runner-pair-approve"));
    expect(onApprove).toHaveBeenCalledOnce();
  });

  it("истёкший на глазах код нельзя подтвердить", () => {
    mount({
      state: { kind: "pending", info: INFO },
      now: Date.parse("2026-10-30T09:51:00Z"),
    });
    expect(screen.getByTestId("runner-pair-approve")).toBeDisabled();
    expect(screen.getByTestId("runner-pair-countdown")).toHaveTextContent(
      "срок вышел",
    );
  });

  it.each([
    ["approved", "Вернитесь в Студию"],
    ["denied", "Устройство не получит доступ."],
    ["expired", "Начните подключение в Студии заново."],
    ["invalid", "Проверьте его в Студии."],
    ["used", "Код уже использован"],
    ["disabled", "Личные раннеры выключены"],
    ["limit", "Достигнут предел раннеров"],
  ] as const)("итог %s", (result, text) => {
    mount({ state: { kind: "result", result } });
    const block = screen.getByTestId("runner-pair-result");
    expect(block).toHaveAttribute("data-state", result);
    expect(block).toHaveTextContent(text);
  });

  it("ввод кода без адреса: маска и проверка", async () => {
    const onCode = vi.fn();
    mount({ onCode });
    await userEvent.type(
      screen.getByTestId("runner-pair-code-input"),
      "lmnp6789",
    );
    await userEvent.click(screen.getByTestId("runner-pair-code-continue"));
    expect(onCode).toHaveBeenCalledWith("LMNP-6789");
  });
});
