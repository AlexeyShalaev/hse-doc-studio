import {
  GALLERY_PROJECT_ID,
  type GalleryGroup,
} from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { BundleExchangeDialog } from "../ui/BundleExchangeDialog";
import { BundleExportDialog } from "../ui/BundleExportDialog";
import { BundleImportDialog } from "../ui/BundleImportDialog";
import { ReadOnlyImport } from "./ReadOnlyImport";
import { CiCard } from "../ui/CiCard";
import { CiGeneratorDialog } from "../ui/CiGeneratorDialog";
import { ExchangeCard } from "../ui/ExchangeCard";

const noop = (): void => undefined;

/**
 * Обмен файлом и автосборка на демо-API: файл выгружается и загружается в
 * памяти вкладки. В демо имя файла со словом «broken» не читается, а файл
 * .hseenc просит пароль («wrong» отвергается).
 */
export const getExchangeGallery = (): GalleryGroup[] => [
  {
    id: "exchange-bundle",
    title: "Обмен файлом без сервера (живой)",
    entries: [
      {
        id: "live_exchange_card",
        title: "Карточка в настройках проекта",
        note: "Две строки: выгрузить проект в файл и загрузить файл от коллеги.",
        scenario: "up_to_date",
        frame: "window",
        render: () => <ExchangeCard projectId={GALLERY_PROJECT_ID} />,
      },
      {
        id: "live_exchange_dialog",
        title: "Окно «Обмен файлом»",
        note: "Открывается со страницы истории, где репозитория ещё нет.",
        scenario: "not_connected",
        frame: "plain",
        render: () => (
          <DialogLauncher label="Открыть окно" defaultOpen>
            {({ isOpen, close }) => (
              <BundleExchangeDialog
                isOpen={isOpen}
                projectId={GALLERY_PROJECT_ID}
                onClose={close}
              />
            )}
          </DialogLauncher>
        ),
      },
      {
        id: "live_exchange_export",
        title: "Выгрузка в файл",
        note: "Пароль необязателен; при вводе просит повторить; итог с кнопкой «Скачать ещё раз».",
        scenario: "up_to_date",
        frame: "plain",
        render: () => (
          <DialogLauncher label="Открыть окно" defaultOpen>
            {({ isOpen, close }) => (
              <BundleExportDialog
                isOpen={isOpen}
                projectId={GALLERY_PROJECT_ID}
                onClose={close}
              />
            )}
          </DialogLauncher>
        ),
      },
      {
        id: "live_exchange_import",
        title: "Загрузка файла",
        note: "Выбор или перетаскивание файла, пароль, ход, итог или переход к конфликтам.",
        scenario: "up_to_date",
        frame: "plain",
        render: () => (
          <DialogLauncher label="Открыть окно" defaultOpen>
            {({ isOpen, close }) => (
              <BundleImportDialog
                isOpen={isOpen}
                projectId={GALLERY_PROJECT_ID}
                onClose={close}
                onNavigate={noop}
              />
            )}
          </DialogLauncher>
        ),
      },
      {
        id: "live_exchange_import_disabled",
        title: "Загрузка недоступна",
        note: "Проект только для чтения: окно называет причину и ничего не принимает.",
        scenario: "up_to_date",
        frame: "plain",
        render: () => (
          <DialogLauncher label="Открыть окно" defaultOpen>
            {({ isOpen, close }) => (
              <ReadOnlyImport isOpen={isOpen} onClose={close} />
            )}
          </DialogLauncher>
        ),
      },
    ],
  },
  {
    id: "exchange-ci",
    title: "Автосборка (живая)",
    entries: [
      {
        id: "live_ci_card",
        title: "Карточка в настройках проекта",
        note: "Что это даёт и кнопка, открывающая окно.",
        scenario: "up_to_date",
        frame: "window",
        render: () => <CiCard projectId={GALLERY_PROJECT_ID} />,
      },
      {
        id: "live_ci_dialog",
        title: "Окно настройки автосборки",
        note: "GitHub или GitLab, что собирать и когда, просмотр файла и запись в проект.",
        scenario: "up_to_date",
        frame: "plain",
        render: () => (
          <DialogLauncher label="Открыть окно" defaultOpen>
            {({ isOpen, close }) => (
              <CiGeneratorDialog
                isOpen={isOpen}
                projectId={GALLERY_PROJECT_ID}
                onClose={close}
              />
            )}
          </DialogLauncher>
        ),
      },
    ],
  },
];
