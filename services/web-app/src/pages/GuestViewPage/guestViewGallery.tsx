import type { GalleryGroup } from "@shared/lib/stateGallery";
import { GuestView } from "./GuestView";

/** Просмотр PDF для читателя без исходников (10.4). */
export const getGuestViewGallery = (): GalleryGroup[] => [
  {
    id: "guest-view",
    title: "Просмотр PDF по ссылке",
    entries: [
      {
        id: "guest_view_docs",
        title: "Документы: собран и не собран",
        frame: "window",
        width: 960,
        render: () => (
          <GuestView
            projectName="ВКР: Анализ требований"
            status="ready"
            embed={false}
            docs={[
              {
                id: "vkr",
                name: "Пояснительная записка",
                pdfUrl: "#vkr",
                pages: 64,
              },
              {
                id: "tz",
                name: "Техническое задание",
                pdfUrl: null,
                pages: null,
              },
            ]}
          />
        ),
      },
      {
        id: "guest_view_empty",
        title: "Документов нет",
        frame: "window",
        width: 720,
        render: () => (
          <GuestView
            projectName="ВКР: Анализ требований"
            status="ready"
            docs={[]}
          />
        ),
      },
    ],
  },
];
