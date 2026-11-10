import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { SignatureOverlay } from "./SignatureOverlay";

// Рамка без картинки на превью: название слота переносится внутри рамки со своим интервалом строк,
// а не наследует lineHeight: 0 страницы PDF (тогда «АКАДЕМИЧЕСКИЙ» и «РУКОВОДИТЕЛЬ» совпадали).

const mount = (widthMm: number) =>
  render(
    <I18nextProvider i18n={i18n}>
      <div style={{ lineHeight: 0, position: "relative" }}>
        <SignatureOverlay
          pngUrl={null}
          label="Академический руководитель"
          xMm={150}
          yMm={250}
          widthMm={widthMm}
          aspectRatio={0.4}
          pageWidthMm={210}
          pageHeightMm={297}
          pxPerMm={3}
          onCommit={() => undefined}
        />
      </div>
    </I18nextProvider>,
  );

describe("SignatureOverlay: подпись пустой рамки", () => {
  it("узкая рамка: перенос в две строки со своим интервалом", () => {
    mount(40);
    const label = screen.getByTestId("signature-frame-label");
    expect(label).toHaveTextContent("Академический руководитель");
    expect(label.style.lineHeight).toBe("1.15");
    expect(label.style.overflow).toBe("hidden");
    expect(label.style.webkitLineClamp).toBe("2");
  });

  it("широкая рамка: одна строка обычным кеглем", () => {
    mount(150);
    const label = screen.getByTestId("signature-frame-label");
    expect(label.style.fontSize).toBe("10px");
    expect(label.style.webkitLineClamp).toBe("1");
  });
});
