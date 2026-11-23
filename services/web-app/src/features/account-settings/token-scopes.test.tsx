import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { ApiToken } from "@entities/session";
import { offeredScopes, scopeDiff, touchesMcp } from "./lib/tokens";
import { TokenScopesDialog } from "./ui/TokenScopesDialog";
import { TokensCard } from "./ui/TokensCard";

const TOKEN: ApiToken = {
  id: "t1",
  name: "Claude Code",
  prefix: "hsd_pat_9Zr",
  scopes: ["api", "mcp"],
  created_at: "2026-09-01T09:00:00Z",
  expires_at: null,
  last_used_at: null,
  origin: "manual",
  client_name: null,
  client_kind: null,
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

afterEach(() => {
  cleanup();
});

describe("права токена: правила показа", () => {
  it("«MCP: администрирование» только админу, но выданное право видно всегда", () => {
    expect(offeredScopes(false)).not.toContain("mcp:admin");
    expect(offeredScopes(true)).toContain("mcp:admin");
    expect(
      offeredScopes(false, { ...TOKEN, scopes: ["mcp", "mcp:admin"] }),
    ).toContain("mcp:admin");
  });

  it("токену устройства только git", () => {
    expect(
      offeredScopes(true, { scopes: ["git:read"], origin: "device" }),
    ).toEqual(["git:read", "git:write"]);
  });

  it("сводка в порядке показа и признак MCP", () => {
    const diff = scopeDiff(["api", "mcp"], ["packs", "git:read", "mcp"]);
    expect(diff).toEqual({ added: ["git:read", "packs"], removed: ["api"] });
    expect(touchesMcp(diff)).toBe(true);
    expect(touchesMcp(scopeDiff(["api"], ["api", "git:read"]))).toBe(false);
  });
});

describe("окно «Изменить права»", () => {
  it("из списка: отмечены нынешние права, сводка, сохранение и подсказка про переподключение", async () => {
    const user = userEvent.setup();
    const onUpdateScopes = vi.fn(
      (_id: string, _scopes: string[], done: () => void) => {
        done();
      },
    );
    render(
      <TokensCard
        status="ready"
        tokens={[TOKEN]}
        onCreate={vi.fn()}
        onRevoke={vi.fn()}
        onUpdateScopes={onUpdateScopes}
      />,
    );

    await user.click(screen.getByTestId("token-edit-t1"));
    const form = await screen.findByTestId("token-scopes-form");
    expect(within(form).getByTestId("token-edit-scope-api")).toBeChecked();
    expect(within(form).getByTestId("token-edit-scope-mcp")).toBeChecked();
    expect(
      within(form).getByTestId("token-edit-scope-packs"),
    ).not.toBeChecked();
    expect(within(form).queryByTestId("token-edit-scope-mcpAdmin")).toBeNull();
    expect(screen.getByTestId("token-scopes-next")).toBeDisabled();

    await user.click(within(form).getByTestId("token-edit-scope-packs"));
    await user.click(within(form).getByTestId("token-edit-scope-api"));
    await user.click(screen.getByTestId("token-scopes-next"));

    expect(
      within(screen.getByTestId("token-scopes-added")).getByText(
        "Студия шаблонов",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("token-scopes-removed")).getByText("API"),
    ).toBeInTheDocument();
    expect(onUpdateScopes).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("token-scopes-save"));

    expect(onUpdateScopes).toHaveBeenCalledWith(
      "t1",
      ["mcp", "packs"],
      expect.any(Function),
    );
    expect(screen.getByTestId("token-scopes-done")).toBeInTheDocument();
    expect(screen.getByTestId("token-scopes-reconnect")).toHaveTextContent(
      /переподключите/,
    );
  });

  it("снять все права нельзя", async () => {
    const user = userEvent.setup();
    render(
      <TokenScopesDialog
        token={{ ...TOKEN, scopes: ["api"] }}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    await user.click(screen.getByTestId("token-edit-scope-api"));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Выберите хотя бы одно право.",
    );
    expect(screen.getByTestId("token-scopes-next")).toBeDisabled();
  });

  it("без MCP-прав подсказки о переподключении нет", async () => {
    const user = userEvent.setup();
    render(
      <TokenScopesDialog
        token={{ ...TOKEN, scopes: ["api"] }}
        onSave={(_scopes, done) => {
          done();
        }}
        onClose={vi.fn()}
      />,
    );
    await user.click(screen.getByTestId("token-edit-scope-gitRead"));
    await user.click(screen.getByTestId("token-scopes-next"));
    await user.click(screen.getByTestId("token-scopes-save"));
    expect(screen.getByTestId("token-scopes-done")).toBeInTheDocument();
    expect(screen.queryByTestId("token-scopes-reconnect")).toBeNull();
  });

  it("отказ сервера показан на сводке, окно не закрывается", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const { rerender } = render(
      <TokenScopesDialog token={TOKEN} onSave={onSave} onClose={vi.fn()} />,
    );
    await user.click(screen.getByTestId("token-edit-scope-sign"));
    await user.click(screen.getByTestId("token-scopes-next"));
    await user.click(screen.getByTestId("token-scopes-save"));
    expect(onSave).toHaveBeenCalledWith(
      ["api", "mcp", "sign"],
      expect.any(Function),
    );

    rerender(
      <TokenScopesDialog
        token={TOKEN}
        failure={{ code: "token_scope_not_allowed" }}
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Такое право этому токену дать нельзя.",
    );
    expect(screen.getByTestId("token-scopes-confirm")).toBeInTheDocument();
  });

  it("у истёкшего токена кнопки нет", () => {
    render(
      <TokensCard
        status="ready"
        tokens={[{ ...TOKEN, expires_at: "2020-01-01T00:00:00Z" }]}
        onCreate={vi.fn()}
        onRevoke={vi.fn()}
        onUpdateScopes={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("token-edit-t1")).toBeNull();
  });

  it("админ видит «MCP: администрирование»", async () => {
    const user = userEvent.setup();
    render(
      <TokensCard
        status="ready"
        instanceAdmin
        tokens={[TOKEN]}
        onCreate={vi.fn()}
        onRevoke={vi.fn()}
        onUpdateScopes={vi.fn()}
      />,
    );
    await user.click(screen.getByTestId("token-edit-t1"));
    expect(
      await screen.findByTestId("token-edit-scope-mcpAdmin"),
    ).not.toBeChecked();
  });
});
