import type { QueryClient } from "@tanstack/react-query";
import { packStudioKeys } from "@entities/pack-studio";
import { CONTENT_TEXT_PATH, CONTENT_VERSION_DIR } from "../content/fixtures";
import { GALLERY_WORKSPACE } from "../galleryKit";

// Замечания к тексту «Технического задания» для записей галереи: ошибка с опечаткой в поле и
// предупреждение про пустое поле, на обеих редакциях (язык интерфейса выбирает одну из них).

export const findingsSeed = (client: QueryClient): void => {
  const findings = ["ru", "en"].flatMap((lang) => {
    const path = CONTENT_TEXT_PATH.replace(".ru.", `.${lang}.`);
    return [
      {
        severity: "error" as const,
        check: "outcome" as const,
        message:
          "Шаблон читает project.meta.name_shrt, а такого поля нет у версии. Возможно, name_short.",
        path,
        line: 6,
        pointer: null,
      },
      {
        severity: "warning" as const,
        check: "lint" as const,
        message: "Поле project.purpose пустое в этом примере данных.",
        path,
        line: 9,
        pointer: null,
      },
    ];
  });
  client.setQueryData(
    packStudioKeys.lint(GALLERY_WORKSPACE.id, CONTENT_VERSION_DIR, "0"),
    {
      scope: "version",
      target: CONTENT_VERSION_DIR,
      released: false,
      errors: 1,
      warnings: 1,
      findings,
    },
  );
};
