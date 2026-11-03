import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n } from "@shared/lib";
import type { AdminUserPasskey } from "@entities/session";
import { ensureAdminUsersLocales } from "./lib/locales";
import { PersonPasskeysView } from "./ui/PersonPasskeys";

const KEYS: AdminUserPasskey[] = [
  {
    id: "pk1",
    name: "MacBook Анны",
    created_at: "2026-11-01T09:30:00Z",
    last_used_at: null,
    synced: true,
    domain: "studio.example.org",
  },
  {
    id: "pk2",
    name: "YubiKey",
    created_at: "2026-10-01T09:30:00Z",
    last_used_at: null,
    synced: false,
    domain: "studio.example.org",
  },
];

beforeAll(async () => {
  await ensureAdminUsersLocales();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});
afterEach(cleanup);

describe("passkey в карточке человека", () => {
  it("число ключей и сброс с подтверждением", async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    render(
      <PersonPasskeysView
        status="ready"
        items={KEYS}
        resetting={false}
        failed={false}
        onReset={onReset}
      />,
    );
    expect(screen.getByTestId("person-passkeys-count")).toHaveTextContent("2");
    expect(screen.getByTestId("person-passkey-pk1")).toHaveTextContent(
      "MacBook Анны",
    );
    await user.click(screen.getByTestId("person-passkeys-reset"));
    expect(onReset).not.toHaveBeenCalled();
    expect(screen.getByText(/сессии не закроются/)).toBeInTheDocument();
    await user.click(screen.getByTestId("person-passkeys-reset-confirm"));
    expect(onReset).toHaveBeenCalled();
  });

  it("без ключей сбрасывать нечего", () => {
    render(
      <PersonPasskeysView
        status="ready"
        items={[]}
        resetting={false}
        failed={false}
        onReset={vi.fn()}
      />,
    );
    expect(screen.getByTestId("person-passkeys-count")).toHaveTextContent(
      "Passkey нет.",
    );
    expect(screen.queryByTestId("person-passkeys-reset")).toBeNull();
  });
});
