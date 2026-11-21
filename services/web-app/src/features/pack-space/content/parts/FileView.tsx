import { useState } from "react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { packFormKind } from "@entities/pack-studio";
import { FormPane } from "../FormPane";
import { TextEditor } from "../text/TextEditor";

// Открытый в «Все файлы» файл: текст с автосохранением (как «Текст» документа) и, у манифестов и
// файлов правил, переключатель на их форму. Файл правил открывается сразу на форме: так его
// правят чаще. Пересоздаётся на каждый файл (`key`), состояние переключателя не переезжает.
export const FileView = ({
  workspaceId,
  path,
  at,
  readOnly,
  onCopy,
  onOpenFile,
}: {
  workspaceId: string;
  path: string;
  at: string | null;
  /** Выпущенная версия: правок нет, есть «Править копию». Файл чужой версии закрывает сервер. */
  readOnly: boolean;
  onCopy: () => void;
  onOpenFile: (path: string) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const kind = packFormKind(path);
  const [view, setView] = useState<"form" | "text">(
    kind === "checks" ? "form" : "text",
  );
  return (
    <div className="sp-ct-fileview" data-testid="ct-fileview">
      {kind !== null && (
        <div
          className="sp-ct-seg sp-ct-fileview-seg"
          role="group"
          aria-label={t("content.parts.files.view")}
        >
          {(["form", "text"] as const).map((item) => (
            <button
              key={item}
              type="button"
              className={clsx("sp-ct-seg-btn", item === view && "on")}
              aria-pressed={item === view}
              data-testid={`ct-fileview-${item}`}
              onClick={() => {
                setView(item);
              }}
            >
              {t(`content.parts.files.${item}`)}
            </button>
          ))}
        </div>
      )}
      {kind !== null && view === "form" ? (
        <FormPane
          workspaceId={workspaceId}
          path={path}
          at={at}
          onOpenFile={onOpenFile}
        />
      ) : (
        <TextEditor
          workspaceId={workspaceId}
          path={path}
          readOnly={readOnly}
          onCopy={onCopy}
        />
      )}
    </div>
  );
};
