import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GitStatusSchema, toStatusView } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import { deriveSyncUi } from "../model/syncUi.model";
import { useSyncText } from "../model/useSyncText";
import { SyncPanelView } from "./SyncPanelView";

// Каждое состояние, которое настоящий бэкенд отдал в сценарии двух Студий
// (contracts/git-sync/live/GitStatus), доходит до панели синхронизации: разбор
// схемой, выбор вида, подписи на обоих языках. Тела снимает backend-тест
// test_live_responses.py.

const LIVE = join(
  import.meta.dirname,
  ...Array<string>(6).fill(".."),
  "contracts",
  "git-sync",
  "live",
  "GitStatus",
);
const NOW = Date.parse("2030-01-01T00:10:00Z");

const snapshots = readdirSync(LIVE)
  .filter((file) => file.endsWith(".json"))
  .sort()
  .map((file) => ({
    name: file.replace(/\.json$/, ""),
    body: JSON.parse(readFileSync(join(LIVE, file), "utf8")) as unknown,
  }));

const handlers = () => ({
  onSync: vi.fn(),
  onCheck: vi.fn(),
  onCancel: vi.fn(),
  onConnect: vi.fn(),
  onFixAccess: vi.fn(),
  onResolve: vi.fn(),
  onOpenSettings: vi.fn(),
  onOpenProfile: vi.fn(),
  onAcknowledgeSharedFolder: vi.fn(),
  onShowInHistory: vi.fn(),
  onSelectIncoming: vi.fn(),
});

const Panel = ({ body }: { body: unknown }) => {
  const status = toStatusView(GitStatusSchema.parse(body));
  const ui = deriveSyncUi(status, { online: true, readOnly: false });
  const text = useSyncText(ui, NOW);
  return (
    <SyncPanelView
      ui={ui}
      status={status}
      text={text}
      now={NOW}
      isStarting={false}
      isChecking={false}
      isCancelling={false}
      selectedIncomingId={null}
      {...handlers()}
    />
  );
};

describe.each(["ru", "en"])("состояния настоящего бэкенда: %s", (language) => {
  beforeEach(async () => {
    await i18n.changeLanguage(language);
  });
  afterEach(cleanup);

  it.each(snapshots.map((snapshot) => [snapshot.name, snapshot.body] as const))(
    "%s рисуется панелью и называет своё состояние",
    (_name, body) => {
      const status = toStatusView(GitStatusSchema.parse(body));
      const ui = deriveSyncUi(status, { online: true, readOnly: false });
      // Состояние выбирает сервер, клиент не придумывает своё и не прячет элемент.
      expect(ui.visible).toBe(true);
      expect(ui.state).toBe(status.ui_state);

      render(<Panel body={body} />);
      expect(
        screen.queryByTestId("sync-panel") ??
          screen.getByTestId("sync-panel-empty"),
      ).toBeInTheDocument();
      // Ни одного непереведённого ключа в панели.
      expect(document.body.textContent).not.toMatch(
        /gitSync:|control\.status|control\.label/,
      );
    },
  );
});
