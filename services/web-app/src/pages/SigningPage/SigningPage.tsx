import { useState } from "react";
import { useParams } from "react-router";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { useSigningPage } from "./model/useSigningPage";
import { SigningView } from "./ui/SigningView";

/**
 * Страница подписанта `/sign/:projectId/:routeId` (docs/design/signing-route.md, 3.2).
 * Ссылка из письма и «Входящих» без токена: не вошедшего шлюз ведёт на вход с `?next=`,
 * не участника проекта страница приглашения возвращает сюда же после «Принять».
 *
 * Подпись на странице (картинка, ЭП, КриптоПро, готовая подпись) подключит срез W5 через
 * `extension` вида (`SigningExtension`, model/extension.ts).
 */
export const SigningPage = () => {
  const { projectId = "", routeId = "" } = useParams<{
    projectId: string;
    routeId: string;
  }>();
  const page = useSigningPage(projectId, routeId);
  // Срок сверяется с моментом открытия: страница живёт недолго, тикать часами незачем.
  const [now] = useState(() => Date.now());
  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />
      <SigningView
        state={page.state}
        now={now}
        busy={page.busy}
        approving={page.approving}
        failure={page.failure}
        onDismissFailure={page.dismissFailure}
        onApprove={() => {
          page.approve();
        }}
        onReturn={page.returnForRework}
        onRetry={page.retry}
        slot={page.slot}
      />
      <AppStatusBar />
    </div>
  );
};
