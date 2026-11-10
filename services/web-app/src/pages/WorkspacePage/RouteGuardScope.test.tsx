import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { documentKeys } from "@entities/document";
import { projectKeys } from "@entities/project";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import { signingRouteKeys, useRouteEditGuard } from "@entities/signing-route";
import {
  SR_DOC,
  SR_PROJECT_ID,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import { RouteGuardScope } from "./RouteGuardScope";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const SERVER = JSON.parse(
  readFileSync(
    join(
      import.meta.dirname,
      "../../../../..",
      "contracts/server/fixtures/Bootstrap/server_user.json",
    ),
    "utf8",
  ),
) as Bootstrap;

const Edit = ({ action }: { action: () => void }) => {
  const guard = useRouteEditGuard(SR_PROJECT_ID);
  return (
    <button
      type="button"
      onClick={() => {
        guard.run({ paths: [`${SR_DOC.doc_id}/sections/a.tex`] }, action);
      }}
    >
      edit
    </button>
  );
};

let routeSeq = 0;

const renderScope = ({
  bootstrap = SERVER,
  role = "editor",
  viaLink = false,
}: {
  bootstrap?: Bootstrap;
  role?: string;
  viaLink?: boolean;
} = {}) => {
  vi.spyOn(apiClient, "get").mockImplementation(
    () => new Promise(() => undefined),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  client.setQueryData(projectKeys.detail(SR_PROJECT_ID), {
    id: SR_PROJECT_ID,
    my_role: role,
    via_link: viaLink,
  });
  client.setQueryData(documentKeys.lists(SR_PROJECT_ID), [
    {
      id: SR_DOC.doc_id,
      source_file: `${SR_DOC.doc_id}/topic.tex`,
      name: SR_DOC.name,
      status: "ok",
    },
  ]);
  // Ответы помнятся на всю вкладку (память модуля): у каждого теста свой маршрут.
  routeSeq += 1;
  client.setQueryData(signingRouteKeys.list(SR_PROJECT_ID, null), {
    items: [
      makeSigningRouteSummary({
        id: `sr_scope_${String(routeSeq)}`,
        docs: [SR_DOC.doc_id],
      }),
    ],
  });
  const action = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <RouteGuardScope projectId={SR_PROJECT_ID}>
        <Edit action={action} />
      </RouteGuardScope>
    </QueryClientProvider>,
  );
  return { action };
};

describe("RouteGuardScope", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    window.sessionStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("asks an editor on the server, the document found by its folder", async () => {
    const user = userEvent.setup();
    const { action } = renderScope();
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(
      await screen.findByRole("dialog", { name: "Документ на подписании" }),
    ).toBeInTheDocument();
    expect(action).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(action).toHaveBeenCalledTimes(1);
    // Ответ лёг в sessionStorage вкладки.
    expect(
      Object.keys(window.sessionStorage).some((key) =>
        key.startsWith(`hds.route-guard.${SR_PROJECT_ID}.${SR_DOC.doc_id}.`),
      ),
    ).toBe(true);
  });

  it.each([
    ["the local Studio", { bootstrap: LOCAL_BOOTSTRAP }],
    ["a reader", { role: "reader" }],
    ["a person who came by a link", { viaLink: true }],
  ])("does not ask %s", async (_who, options) => {
    const user = userEvent.setup();
    const { action } = renderScope(options);
    await user.click(screen.getByRole("button", { name: "edit" }));
    expect(action).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
