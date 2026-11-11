import { useTranslation } from "react-i18next";
import { Button, Modal } from "@shared/ui";
import { DialogLauncher } from "@shared/ui/StateGallery";
import type { RunnerDiskView } from "../model/runnerDisk.schema";
import { RunnerDiskPanel } from "./RunnerDiskPanel";

const noop = () => undefined;

/** Галерея: окно «Диск» по кнопке, с панелью на эталоне вместо запросов. */
export const RunnerDiskDialogPreview = ({
  view,
  runnerName,
}: {
  view: RunnerDiskView;
  runnerName: string;
}) => {
  const { t } = useTranslation("runnerDisk");
  return (
    <DialogLauncher label="Открыть окно «Диск»">
      {({ isOpen, close }) => (
        <Modal
          isOpen={isOpen}
          onClose={close}
          width={640}
          title={t("title", { name: runnerName })}
          footer={
            <Button type="button" variant="ghost" onClick={close}>
              {t("close")}
            </Button>
          }
        >
          <RunnerDiskPanel
            view={view}
            runnerName={runnerName}
            onRefresh={noop}
            onClean={noop}
            onCancel={noop}
          />
        </Modal>
      )}
    </DialogLauncher>
  );
};
