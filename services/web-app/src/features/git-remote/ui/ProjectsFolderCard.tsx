import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import { useCapabilities } from "@entities/session";
import { toast } from "@shared/lib";
import { Button, Input } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import { AccessCard } from "./AccessCard";

// Куда Студия сама кладёт проекты, открытые из облака. Пусто: стандартная папка проектов.
// Только локальная Студия: на сервере папки проектов выбирает сервер.
export const ProjectsFolderCard = () => {
  const { t } = useTranslation("gitAccess");
  const { lacks } = useCapabilities();
  const settings = useAppSettings();
  const update = useUpdateAppSettings();
  const [draft, setDraft] = useState<string | null>(null);
  if (lacks("git_server_login")) return null;

  const saved = settings.data?.projects_dir ?? "";
  const value = draft ?? saved;
  const changed = value.trim() !== saved;

  const save = (next: string | null) => {
    update.mutate(
      { projects_dir: next },
      {
        onSuccess: () => {
          setDraft(null);
          toast.success(t("access.projectsDir.saved"));
        },
      },
    );
  };

  return (
    <AccessCard
      id="git-access-projects-dir"
      title={t("access.projectsDir.title")}
      description={t("access.projectsDir.text")}
    >
      <form
        className="flex flex-col"
        style={{ gap: 8 }}
        onSubmit={(event) => {
          event.preventDefault();
          if (changed) save(value.trim() === "" ? null : value.trim());
        }}
      >
        <Input
          label={t("access.projectsDir.label")}
          value={value}
          placeholder={t("access.projectsDir.placeholder")}
          hint={t("access.projectsDir.hint")}
          spellCheck={false}
          disabled={settings.isPending}
          onChange={(event) => {
            setDraft(event.target.value);
          }}
          data-testid="projects-dir-input"
        />
        <div className="flex items-center" style={{ gap: 8 }}>
          <Button
            type="submit"
            disabled={!changed || update.isPending}
            data-testid="projects-dir-save"
          >
            {t("access.projectsDir.save")}
          </Button>
          {saved !== "" && (
            <Button
              type="button"
              variant="ghost"
              disabled={update.isPending}
              onClick={() => {
                save(null);
              }}
              data-testid="projects-dir-reset"
            >
              {t("access.projectsDir.reset")}
            </Button>
          )}
          {(settings.isPending || update.isPending) && <Spinner size="sm" />}
        </div>
        {update.isError && (
          <Notice
            tone="err"
            role="alert"
            text={t("access.projectsDir.failed")}
          />
        )}
      </form>
    </AccessCard>
  );
};
