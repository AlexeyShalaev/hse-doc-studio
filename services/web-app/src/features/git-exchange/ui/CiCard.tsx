import { useState } from "react";
import { Workflow } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CiGeneratorDialog } from "./CiGeneratorDialog";

export type CiCardProps = {
  projectId: string;
};

// Раздел «Автосборка (CI)» в настройках проекта: что это даёт и кнопка, которая
// открывает окно настройки. Заголовок рисует страница.
export const CiCard = ({ projectId }: CiCardProps) => {
  const { t } = useTranslation("gitExchange");
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col" style={{ gap: 12 }} data-testid="ci-card">
      <p
        className="dim"
        style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55 }}
      >
        {t("card.ci.lead")}
      </p>
      <div>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setOpen(true);
          }}
        >
          <Workflow size={13} aria-hidden="true" />
          {t("card.ci.action")}
        </button>
      </div>
      <CiGeneratorDialog
        isOpen={open}
        projectId={projectId}
        onClose={() => {
          setOpen(false);
        }}
      />
    </div>
  );
};
