import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import type { CollabSnapshot } from "../lib/collabProvider";
import { CollabBadge } from "./CollabBadge";

const snapshot = (over: Partial<CollabSnapshot> = {}): CollabSnapshot => ({
  status: "connected",
  synced: true,
  everSynced: true,
  canWrite: true,
  refusal: null,
  peers: [],
  problem: null,
  ...over,
});

const mount = (value: CollabSnapshot) =>
  render(
    <I18nextProvider i18n={i18n}>
      <CollabBadge snapshot={value} />
    </I18nextProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});
afterEach(cleanup);

describe("CollabBadge", () => {
  it("shows the connection state and the people in the file", () => {
    mount(
      snapshot({
        peers: [
          {
            clientId: 1,
            name: "Борис Иванов",
            color: "#2f9e44",
            writable: true,
          },
          {
            clientId: 2,
            name: "Гость: Вера",
            color: "#1c7ed6",
            writable: false,
          },
        ],
      }),
    );

    expect(screen.getByTestId("collab-badge").dataset.status).toBe("connected");
    expect(screen.getByLabelText("Борис Иванов").textContent).toBe("БИ");
    expect(screen.getByLabelText("Гость: Вера").textContent).toBe("В");
    expect(screen.getByTestId("collab-peers").dataset.tt).toContain(
      "Борис Иванов, Гость: Вера",
    );
  });

  it("marks a reader and an offline connection", () => {
    mount(snapshot({ canWrite: false, status: "offline", synced: false }));

    expect(screen.getByTestId("collab-readonly")).toBeTruthy();
    expect(screen.getByTestId("collab-badge").dataset.status).toBe("offline");
  });

  it("surfaces a server problem instead of the status text", () => {
    mount(snapshot({ problem: "save_failed" }));

    expect(screen.getByRole("status").dataset.tt).toContain("не смог записать");
  });
});
