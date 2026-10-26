import { describe, expect, it } from "vitest";
import { GIT_UI_STATES } from "@entities/git-sync";
import {
  commit,
  connected,
  noRemote,
  runningOperation,
} from "../testing/statusFactory";
import { deriveSyncUi, type SyncUiContext } from "./syncUi.model";

const ONLINE: SyncUiContext = { online: true, readOnly: false };

const STATES_WITH_SYNC = [
  "unfetched",
  "up_to_date",
  "ahead",
  "behind",
  "diverged",
];

describe("deriveSyncUi", () => {
  it("hides the control on a backend without sync", () => {
    expect(deriveSyncUi(noRemote(false), ONLINE).visible).toBe(false);
    expect(deriveSyncUi(undefined, ONLINE).visible).toBe(false);
  });

  it("covers every server state with a unique icon/label pair", () => {
    const seen = new Set<string>();
    for (const state of GIT_UI_STATES) {
      const status =
        state === "no_remote"
          ? noRemote()
          : connected({
              ui_state: state,
              blocked: state === "blocked" ? { reason: "off_branch" } : null,
              operation: state === "syncing" ? runningOperation() : null,
              pending:
                state === "conflicts"
                  ? { session_id: "s", files_total: 3, files_open: 2 }
                  : null,
            });
      const ui = deriveSyncUi(status, ONLINE);
      expect(ui.visible).toBe(true);
      expect(ui.state).toBe(state);
      // Значок и подпись есть всегда: цвет не несёт смысл в одиночку.
      expect(ui.icon).not.toBe("");
      expect(ui.labelKey).not.toBe("");
      seen.add(`${ui.icon}|${ui.labelKey}`);
    }
    expect(seen.size).toBe(GIT_UI_STATES.length);
  });

  it("keeps the exact tone, icon and primary action per state", () => {
    const row = (state: string, extra = {}) => {
      const ui = deriveSyncUi(connected({ ui_state: state, ...extra }), ONLINE);
      return [ui.tone, ui.icon, ui.primary];
    };
    expect(row("up_to_date")).toEqual(["ok", "cloud_check", "sync"]);
    expect(row("ahead", { ahead: 2 })).toEqual([
      "info",
      "cloud_upload",
      "sync",
    ]);
    expect(row("behind", { behind: 3 })).toEqual([
      "accent",
      "cloud_download",
      "sync",
    ]);
    expect(row("diverged", { ahead: 1, behind: 2 })).toEqual([
      "info",
      "git_merge",
      "sync",
    ]);
    expect(row("auth_failed")).toEqual(["err", "key", "fix_access"]);
    expect(row("offline")).toEqual(["warn", "wifi_off", "retry"]);
    expect(row("error")).toEqual(["err", "alert_circle", "details"]);
    expect(
      row("conflicts", {
        pending: { session_id: "s", files_total: 3, files_open: 3 },
      }),
    ).toEqual(["err", "alert_triangle", "resolve"]);
    expect(deriveSyncUi(noRemote(), ONLINE)).toMatchObject({
      tone: "muted",
      icon: "cloud_off",
      primary: "connect",
    });
  });

  it("treats an unknown server state like a failure, not a crash", () => {
    const ui = deriveSyncUi(connected({ ui_state: "from_the_future" }), ONLINE);
    expect(ui.state).toBe("unknown");
    expect(ui.tone).toBe("err");
    expect(ui.primary).toBe("details");
  });

  it("carries the counts shown on the button", () => {
    const ui = deriveSyncUi(
      connected({
        ui_state: "diverged",
        ahead: 2,
        behind: 3,
        incoming: [commit("a1")],
      }),
      ONLINE,
    );
    expect(ui).toMatchObject({ incoming: 3, outgoing: 2 });
    expect(ui.statusKey).toBe("control.status.diverged");
    expect(ui.statusParams).toMatchObject({ incoming: 3, outgoing: 2 });
  });

  it("reports the open files for conflicts", () => {
    const ui = deriveSyncUi(
      connected({
        ui_state: "conflicts",
        pending: { session_id: "s", files_total: 5, files_open: 3 },
      }),
      ONLINE,
    );
    expect(ui.conflictFiles).toBe(3);
    expect(ui.statusParams.count).toBe(3);
    expect(ui.railBadge).toEqual({ tone: "err", count: 3 });
  });

  it("shows phase and percent of a running operation", () => {
    const ui = deriveSyncUi(
      connected({
        ui_state: "syncing",
        operation: runningOperation({ phase: "push", percent: 62 }),
      }),
      ONLINE,
    );
    expect(ui).toMatchObject({ busy: true, phase: "push", percent: 62 });
    expect(ui.canSync).toBe(false);
    expect(ui.canCheck).toBe(false);
  });

  it("marks operations that are not a sync", () => {
    const ui = deriveSyncUi(
      connected({
        ui_state: "syncing",
        operation: runningOperation({ kind: "bundle_import" }),
      }),
      ONLINE,
    );
    expect(ui.operationKind).toBe("bundle_import");
  });

  describe("rail badge priority", () => {
    it("conflicts > no access or error > incoming > nothing", () => {
      const badge = (status: Parameters<typeof deriveSyncUi>[0]) =>
        deriveSyncUi(status, ONLINE).railBadge;
      expect(
        badge(
          connected({
            ui_state: "conflicts",
            pending: { session_id: "s", files_total: 2, files_open: 2 },
          }),
        ),
      ).toEqual({ tone: "err", count: 2 });
      expect(badge(connected({ ui_state: "auth_failed" }))).toEqual({
        tone: "warn",
        count: 1,
      });
      expect(badge(connected({ ui_state: "error" }))).toEqual({
        tone: "warn",
        count: 1,
      });
      expect(badge(connected({ ui_state: "behind", behind: 4 }))).toEqual({
        tone: "info",
        count: 4,
      });
      expect(badge(connected({ ui_state: "up_to_date" }))).toBeNull();
      expect(badge(connected({ ui_state: "ahead", ahead: 3 }))).toBeNull();
      expect(badge(noRemote())).toBeNull();
    });
  });

  describe("online and offline", () => {
    it.each(STATES_WITH_SYNC)(
      "%s becomes offline without a network and cannot sync",
      (state) => {
        const ui = deriveSyncUi(connected({ ui_state: state }), {
          online: false,
          readOnly: false,
        });
        expect(ui.state).toBe("offline");
        expect(ui.blockReason).toBe("offline_browser");
        expect(ui.canSync).toBe(false);
        expect(ui.canCheck).toBe(false);
        expect(ui.statusKey).toBe("control.status.offline_browser");
        expect(ui.primary).toBe("details");
      },
    );

    it("does not hide a running operation or open conflicts when offline", () => {
      const syncing = deriveSyncUi(
        connected({ ui_state: "syncing", operation: runningOperation() }),
        { online: false, readOnly: false },
      );
      expect(syncing.state).toBe("syncing");
      const conflicts = deriveSyncUi(
        connected({
          ui_state: "conflicts",
          pending: { session_id: "s", files_total: 1, files_open: 1 },
        }),
        { online: false, readOnly: false },
      );
      expect(conflicts.state).toBe("conflicts");
    });

    it("lets a server-side offline state retry once the browser is online", () => {
      const ui = deriveSyncUi(connected({ ui_state: "offline" }), ONLINE);
      expect(ui.blockReason).toBeNull();
      expect(ui.canSync).toBe(true);
      expect(ui.primary).toBe("retry");
    });

    it("a project without a remote stays connectable offline", () => {
      const ui = deriveSyncUi(noRemote(), { online: false, readOnly: false });
      expect(ui.state).toBe("no_remote");
      expect(ui.primary).toBe("connect");
    });
  });

  describe("read only", () => {
    it.each(STATES_WITH_SYNC)(
      "%s becomes blocked read_only; sync is off, a check is allowed",
      (state) => {
        const ui = deriveSyncUi(connected({ ui_state: state }), {
          online: true,
          readOnly: true,
        });
        expect(ui.state).toBe("blocked");
        expect(ui.blockReason).toBe("read_only");
        expect(ui.canSync).toBe(false);
        expect(ui.canCheck).toBe(true);
        expect(ui.labelKey).toBe("control.label.blocked_read_only");
      },
    );

    it("a read-only project cannot get a remote connected", () => {
      const ui = deriveSyncUi(noRemote(), { online: true, readOnly: true });
      expect(ui.primary).toBe("details");
      expect(ui.blockReason).toBe("read_only");
    });

    it("keeps the reason the server gave when it already blocked", () => {
      const ui = deriveSyncUi(
        connected({
          ui_state: "blocked",
          blocked: { reason: "remote_schema_newer", required_studio: "0.4.0" },
        }),
        ONLINE,
      );
      expect(ui.blockReason).toBe("remote_schema_newer");
      expect(ui.requiredStudio).toBe("0.4.0");
      expect(ui.canCheck).toBe(false);
      expect(ui.labelKey).toBe("control.label.blocked_remote_schema_newer");
    });

    it("an unknown blocked reason falls back to a generic one", () => {
      const ui = deriveSyncUi(
        connected({ ui_state: "blocked", blocked: { reason: "newfangled" } }),
        ONLINE,
      );
      expect(ui.blockReason).toBe("unknown");
    });
  });

  it("announces stops loudly and good news politely", () => {
    const announce = (state: string) =>
      deriveSyncUi(connected({ ui_state: state }), ONLINE).announce;
    expect(announce("conflicts")).toBe("assertive");
    expect(announce("auth_failed")).toBe("assertive");
    expect(announce("error")).toBe("assertive");
    expect(announce("up_to_date")).toBe("polite");
    expect(announce("behind")).toBe("polite");
    expect(announce("ahead")).toBeNull();
  });

  it("uses a plain sentence for up to date when nothing was ever synced", () => {
    const ui = deriveSyncUi(
      connected({
        ui_state: "up_to_date",
        last_sync_at: null,
        last_sync: null,
        last_fetch_ok_at: null,
      }),
      ONLINE,
    );
    expect(ui.statusKey).toBe("control.status.up_to_date_plain");
  });
});
