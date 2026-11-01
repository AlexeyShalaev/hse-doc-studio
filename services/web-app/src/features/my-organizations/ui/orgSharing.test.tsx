import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrgSharingPolicy } from "@entities/share-link";
import { i18n } from "@shared/lib";
import { tightens } from "../lib/sharing";
import { OrgSharingPolicyView } from "./OrgSharingPolicySection";

afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

const POLICY: OrgSharingPolicy = {
  links: "any",
  max_link_role: "editor",
  nda_public_links: false,
  external_invites: true,
  editable: true,
};

describe("политика общего доступа организации", () => {
  it("ужесточение распознаётся", () => {
    expect(tightens(POLICY, { ...POLICY, links: "off" })).toBe(true);
    expect(tightens(POLICY, { ...POLICY, max_link_role: "reader" })).toBe(true);
    expect(tightens({ ...POLICY, links: "off" }, POLICY)).toBe(false);
    expect(tightens(POLICY, { ...POLICY, external_invites: false })).toBe(
      false,
    );
  });

  it("ослабление сохраняется сразу, ужесточение с подтверждением", async () => {
    const onSave = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <OrgSharingPolicyView
          orgName="МСПИН"
          status="ready"
          policy={POLICY}
          onSave={onSave}
        />
      </I18nextProvider>,
    );
    const save = screen.getByTestId<HTMLButtonElement>("org-sharing-save");
    expect(save.disabled).toBe(true);
    await userEvent.click(screen.getByTestId("org-sharing-external-invites"));
    await userEvent.click(save);
    expect(onSave).toHaveBeenCalledWith({ ...POLICY, external_invites: false });
    onSave.mockClear();
    await userEvent.click(screen.getByTestId("org-sharing-nda"));
    await userEvent.click(save);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("участник видит политику только для чтения", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <OrgSharingPolicyView
          orgName="МСПИН"
          status="ready"
          policy={{ ...POLICY, editable: false }}
          onSave={vi.fn()}
        />
      </I18nextProvider>,
    );
    expect(screen.queryByTestId("org-sharing-save")).toBeNull();
    expect(
      screen.getByTestId<HTMLButtonElement>("org-sharing-nda").disabled,
    ).toBe(true);
  });
});
