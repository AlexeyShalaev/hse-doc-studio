import {
  GALLERY_PROJECT_ID,
  type GalleryGroup,
} from "@shared/lib/stateGallery";
import { ConflictScreen } from "../ui/ConflictScreen";

/**
 * Экран разбора конфликтов на демо-данных: в списке файл каждого вида (текст
 * с несколькими местами, JSON с полями, рисунок, удалён и изменён, подпись),
 * автоматически решённые файлы и предупреждения. Решения можно принимать,
 * применять и отменять до конца.
 */
export const getConflictsGallery = (): GalleryGroup[] => [
  {
    id: "conflicts-screen",
    title: "Разбор конфликтов (живой)",
    description:
      "Откройте файлы из списка слева: у каждого вида свой способ решения. «Применить» запускает слияние и показывает ход.",
    entries: [
      {
        id: "live_conflicts",
        title: "Есть конфликты",
        note: "Шесть конфликтующих файлов, группа «Решено автоматически», предупреждения.",
        scenario: "conflicts",
        frame: "screen",
        render: () => <ConflictScreen projectId={GALLERY_PROJECT_ID} />,
      },
      {
        id: "live_no_conflicts",
        title: "Конфликтов нет",
        note: "Адрес открыли без конфликтов: короткое пояснение и выход в историю.",
        scenario: "up_to_date",
        frame: "screen",
        render: () => <ConflictScreen projectId={GALLERY_PROJECT_ID} />,
      },
    ],
  },
];
