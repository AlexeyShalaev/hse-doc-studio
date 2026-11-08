import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { ImageOverlaysNotice } from "./ImageOverlaysNotice";

const SOURCE = "/Users/anna/hse-doc-studio/packs";

describe("ImageOverlaysNotice", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("warns that a mounted template folder stays as it is", () => {
    render(
      <ImageOverlaysNotice
        overlays={[
          { destination: "/app/packs", source: SOURCE, on_update: "keep" },
        ]}
      />,
    );
    expect(
      screen.getByText(
        `Каталог шаблонов подключён из ${SOURCE} и после обновления останется прежним, поэтому может отстать от новой версии. Обновите его вместе со Студией или уберите подключение.`,
      ),
    ).toBeInTheDocument();
  });

  it("says the dev mount is removed and the host folder is untouched", () => {
    render(
      <ImageOverlaysNotice
        overlays={[
          { destination: "/app/packs", source: SOURCE, on_update: "drop" },
        ]}
      />,
    );
    expect(
      screen.getByText(
        /при обновлении снимем: новая версия возьмёт свои файлы/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Папка на компьютере не изменится/),
    ).toBeInTheDocument();
  });

  it("renders nothing without overlays", () => {
    const { container } = render(<ImageOverlaysNotice overlays={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
