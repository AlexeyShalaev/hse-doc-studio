import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { CatalogApplySchema, CatalogCheckSchema } from "../api/schemas";
import { CatalogApplyResult, CatalogCheckReport } from "./CatalogCheckReport";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-catalog/fixtures",
);
const load = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));

describe("отчёт «Проверить»", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru");
  });

  it("можно применить: число новых версий и вердикт каждой версии", () => {
    render(
      <CatalogCheckReport
        check={CatalogCheckSchema.parse(load("CatalogCheck", "ok"))}
      />,
    );
    expect(screen.getByTestId("catalog-check-report")).toHaveAttribute(
      "data-ok",
      "true",
    );
    expect(
      screen.getByText("Можно применить: появятся 2 версии."),
    ).toBeInTheDocument();
    const pack = screen.getByTestId("catalog-pack-acme-thesis");
    expect(within(pack).getAllByText("Появится")).toHaveLength(2);
    const incompatible = screen.getByTestId("catalog-version-thesis@2026.2.0");
    expect(
      within(incompatible).getByText("Не для этой Студии"),
    ).toBeInTheDocument();
    expect(
      within(incompatible).getByText("Нужна Студия 0.99.0 или новее"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("catalog-version-thesis@2026.2.1")).getByText(
        "Не выпущена",
      ),
    ).toBeInTheDocument();
  });

  it("применить нельзя: препятствия словами, конфликты паков, ошибки версий", () => {
    render(
      <CatalogCheckReport
        check={CatalogCheckSchema.parse(load("CatalogCheck", "blocked"))}
      />,
    );
    expect(screen.getByText("Применить нельзя:")).toBeInTheDocument();
    expect(
      screen.getByTestId("catalog-blocker-pack_conflict"),
    ).toHaveTextContent("Пак с таким id уже есть в каталоге");
    expect(
      screen.getByTestId("catalog-blocker-version_changed"),
    ).toHaveTextContent("Её нельзя заменить");
    const builtin = screen.getByTestId("catalog-pack-hse-cs-sse");
    expect(within(builtin).getByText(/встроен в Студию/)).toBeInTheDocument();
    expect(
      within(builtin).getByText("Изменена в источнике"),
    ).toBeInTheDocument();
    const other = screen.getByTestId("catalog-pack-acme-thesis");
    expect(
      within(other).getByText(
        "Пак с таким id уже приходит из источника «Паки кафедры (архив)».",
      ),
    ).toBeInTheDocument();
    expect(
      within(other).getByText(
        "files/thesis/main.tex: \\input{missing} не найден",
      ),
    ).toBeInTheDocument();
    expect(within(other).getByText("changes.en пуст")).toBeInTheDocument();
    expect(
      within(other).getByText(
        "thesis: id шаблона 'vkr' не совпадает с именем папки",
      ),
    ).toBeInTheDocument();
  });

  it("итог применения перечисляет добавленные версии", () => {
    render(
      <CatalogApplyResult
        result={CatalogApplySchema.parse(load("CatalogApply", "applied"))}
      />,
    );
    expect(screen.getByText("Добавлены 2 версии:")).toBeInTheDocument();
    expect(screen.getByText("acme-thesis/thesis@2026.1.1")).toBeInTheDocument();
    expect(screen.getByText("Применена ревизия 4b825dc6.")).toBeInTheDocument();
  });
});
