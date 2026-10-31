import { describe, expect, it } from "vitest";
import { deriveSyncUi } from "../model/syncUi.model";
import { SYNC_STATE_FIXTURES } from "./syncStates";

// Каждое состояние галереи обязано давать тот вид, под которым оно названо:
// иначе владелец продукта смотрит не на то, что думает.
const EXPECTED: Record<string, { state: string; block?: string }> = {
  no_remote: { state: "no_remote" },
  no_remote_read_only: { state: "no_remote", block: "read_only" },
  unfetched: { state: "unfetched" },
  up_to_date: { state: "up_to_date" },
  ahead: { state: "ahead" },
  behind: { state: "behind" },
  diverged: { state: "diverged" },
  syncing_queued: { state: "syncing" },
  syncing_snapshot: { state: "syncing" },
  syncing_fetch: { state: "syncing" },
  syncing_merge: { state: "syncing" },
  syncing_push: { state: "syncing" },
  syncing_bundle: { state: "syncing" },
  conflicts: { state: "conflicts" },
  auth_failed: { state: "auth_failed" },
  offline: { state: "offline" },
  offline_browser: { state: "offline", block: "offline_browser" },
  error_remote_moved: { state: "error" },
  error_large_file: { state: "error" },
  error_push_rejected: { state: "error" },
  error_unknown: { state: "error" },
  blocked_off_branch: { state: "blocked", block: "off_branch" },
  blocked_read_only: { state: "blocked", block: "read_only" },
  blocked_schema_newer: { state: "blocked", block: "remote_schema_newer" },
  blocked_store_untrusted: { state: "blocked", block: "store_untrusted" },
  blocked_profile_required: { state: "blocked", block: "profile_required" },
  shared_folder: { state: "up_to_date" },
  unknown: { state: "unknown" },
};

describe("состояния синхронизации для галереи", () => {
  it("названия не повторяются и каждое описано", () => {
    const ids = SYNC_STATE_FIXTURES.map((fixture) => fixture.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect([...ids].sort()).toEqual(Object.keys(EXPECTED).sort());
  });

  it.each(SYNC_STATE_FIXTURES.map((fixture) => [fixture.id, fixture] as const))(
    "%s даёт заявленный вид",
    (id, fixture) => {
      const ui = deriveSyncUi(fixture.build(Date.now()), {
        online: fixture.context?.online ?? true,
        readOnly: fixture.context?.readOnly ?? false,
      });
      const expected = EXPECTED[id];
      expect(ui.visible).toBe(true);
      expect(ui.state).toBe(expected?.state);
      if (expected?.block) expect(ui.blockReason).toBe(expected.block);
    },
  );

  it("время считается от «сейчас»: подписи не стареют", () => {
    const fixture = SYNC_STATE_FIXTURES.find(
      (item) => item.id === "up_to_date",
    );
    const now = Date.parse("2031-01-01T12:00:00Z");
    const status = fixture?.build(now);
    expect(Date.parse(status?.last_sync_at ?? "")).toBe(now - 3 * 3_600_000);
  });

  it("у конфликтов есть полоса, у остальных нет", () => {
    const banners = SYNC_STATE_FIXTURES.filter((fixture) => fixture.banner);
    expect(banners.map((fixture) => fixture.id)).toEqual(["conflicts"]);
  });
});
