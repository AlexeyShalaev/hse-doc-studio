import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { NowBlock } from "./NowBlock";
import type { DocumentItem } from "./lib/buildDocSections";

const doc = (over: Partial<DocumentItem>): DocumentItem =>
  ({ id: "report", status: "err", ...over }) as unknown as DocumentItem;

const mount = (documents: DocumentItem[]) =>
  render(
    <I18nextProvider i18n={i18n}>
      <NowBlock
        documents={documents}
        forms={[]}
        lang="ru"
        onSelectDoc={() => undefined}
        onOpenForm={() => undefined}
      />
    </I18nextProvider>,
  );

describe("NowBlock: failed builds", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("shows the reason of the failure under the document", () => {
    mount([
      doc({
        last_compile_error: {
          code: "image_missing",
          message: "Не установлен образ TeX Live. Установите его в настройках.",
        },
      }),
    ]);

    expect(screen.getByTestId("now-reason").textContent).toBe(
      "Не установлен образ TeX Live.",
    );
    expect(screen.getByTestId("now-doc:report").title).toContain(
      "Установите его в настройках",
    );
  });

  it("keeps the plain line for a failure recorded without a reason", () => {
    mount([doc({ last_compile_error: null })]);

    expect(screen.queryByTestId("now-reason")).toBeNull();
    expect(screen.getByTestId("now-doc:report")).toBeTruthy();
  });
});
