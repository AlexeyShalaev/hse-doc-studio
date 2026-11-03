import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { useDraft } from "@shared/lib/useDraft";
import type { AdminAuthSettings } from "@entities/session";
import { ensureAdminSettingsLocales } from "./lib/locales";
import { SignInSection, type SignInDraft } from "./ui/SignInSection";

const free = { source: "default", locked: false } as const;
const AUTH: AdminAuthSettings = {
  password_enabled: true,
  oidc_enabled_count: 0,
  fields: { "auth.password_enabled": free, "auth.passkeys_enabled": free },
  passkeys_enabled: true,
  passkey_domain: "studio.example.org",
  passkey_issue: null,
  passkey_domains: [{ domain: "studio.example.org", count: 2 }],
};

const Harness = ({ settings }: { settings: AdminAuthSettings }) => {
  const draft = useDraft<SignInDraft>({
    password: settings.password_enabled,
    passkeys: settings.passkeys_enabled,
  });
  return <SignInSection settings={settings} draft={draft} />;
};

beforeAll(async () => {
  await ensureAdminSettingsLocales();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});
afterEach(cleanup);

describe("passkey в способах входа", () => {
  it("переключатель меняет черновик и показывает домен", () => {
    render(<Harness settings={AUTH} />);
    expect(screen.getByTestId("auth-passkey-domain")).toHaveTextContent(
      "studio.example.org",
    );
    expect(screen.queryByTestId("auth-passkey-stale")).toBeNull();
    expect(screen.getByTestId("auth-passkey-address-hint")).toBeInTheDocument();
    const toggle = screen.getByTestId("auth-passkeys-toggle");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "false");
  });

  it("заданный окружением переключатель не меняется", () => {
    render(
      <Harness
        settings={{
          ...AUTH,
          fields: {
            ...AUTH.fields,
            "auth.passkeys_enabled": { source: "env", locked: true },
          },
        }}
      />,
    );
    expect(screen.getByTestId("auth-passkeys-toggle")).toBeDisabled();
  });

  it("ключи старого адреса и негодный адрес дают предупреждения", () => {
    render(
      <Harness
        settings={{
          ...AUTH,
          passkey_domain: null,
          passkey_issue: "insecure_origin",
          passkey_domains: [{ domain: "old.example.org", count: 5 }],
        }}
      />,
    );
    expect(screen.getByTestId("auth-passkey-issue")).toHaveTextContent("HTTPS");
    expect(screen.getByTestId("auth-passkey-stale")).toHaveTextContent(
      "5 ключей привязаны к old.example.org",
    );
  });

  it("у каждой причины есть текст на обоих языках", async () => {
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const issue of [
        "no_address",
        "insecure_origin",
        "ip_address",
        "rp_id_mismatch",
      ]) {
        expect(
          i18n.exists(`adminSettings:signin.passkeyIssue.${issue}`),
          `${lng} ${issue}`,
        ).toBe(true);
      }
    }
  });
});
