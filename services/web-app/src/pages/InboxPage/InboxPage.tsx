import { InboxPanel } from "@features/inbox";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";

/** «Входящие» (/inbox): приглашения, передачи, запросы доступа и уведомления. */
export const InboxPage = () => (
  <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
    <AppTitlebar />
    <div
      className="flex flex-1 justify-center"
      style={{ overflowY: "auto", minHeight: 0 }}
    >
      <InboxPanel />
    </div>
    <AppStatusBar />
  </div>
);
