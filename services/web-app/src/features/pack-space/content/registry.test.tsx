import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { CONTENT_PARTS, DOC_SEGMENTS } from "./contract";
import { renderSignatures } from "./signatures/signaturesTestKit";
import ContentMain from "./ContentMain";
import { PART_COMPONENTS, SEGMENT_COMPONENTS } from "./registry";

// Контракт точек расширения (docs/design/pack-studio-ux.md, 12.7): на каждый сегмент и раздел
// есть свой файл в `extend/`. Удалить или переименовать его значит сломать срез S8b, S8c или S8d.
describe("файлы-расширения области", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  afterEach(cleanup);

  it.each(DOC_SEGMENTS)("сегмент %s подключён", (segment) => {
    expect(SEGMENT_COMPONENTS[segment]).not.toBeNull();
  });

  it.each(CONTENT_PARTS)("раздел %s подключён", (part) => {
    expect(PART_COMPONENTS[part]).not.toBeNull();
  });

  it("сегмент «Подписи» (S8c) рисуется в рамке документа", async () => {
    renderSignatures(<ContentMain />, "doc=source_listing&seg=signatures");
    expect(await screen.findByTestId("ct-signatures")).toHaveAttribute(
      "data-doc",
      "source_listing",
    );
  });

  it("раздел «Подписи и места» (S8c) рисуется сводкой", async () => {
    renderSignatures(<ContentMain />, "part=signatures");
    expect(await screen.findByTestId("ct-sg-overview")).toBeInTheDocument();
  });
});
