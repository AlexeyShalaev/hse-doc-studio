import { useTranslation } from "react-i18next";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import { toast } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { Select } from "@shared/ui/Select";
import { Spinner } from "@shared/ui/Spinner";
import {
  FALLBACK_FETCH_INTERVAL_S,
  intervalChoices,
  splitInterval,
} from "../model/fetchIntervals";
import { AccessCard } from "./AccessCard";

// Личная настройка приложения: как часто проверять репозитории проектов, у
// которых свой интервал не задан. В проекте её можно переопределить.
export const FetchDefaultCard = () => {
  const { t } = useTranslation("gitAccess");
  const { t: tRemote } = useTranslation("gitRemote");
  const settings = useAppSettings();
  const update = useUpdateAppSettings();
  const current =
    settings.data?.git_fetch_interval_s ?? FALLBACK_FETCH_INTERVAL_S;

  const label = (seconds: number): string => {
    const { unit, count } = splitInterval(seconds);
    return tRemote(`settings.interval.${unit}`, { count });
  };
  const options = [
    { value: "0", label: t("access.fetchDefault.off") },
    ...intervalChoices(current).map((seconds) => ({
      value: String(seconds),
      label: label(seconds),
    })),
  ];

  return (
    <AccessCard
      id="git-access-fetch"
      title={t("access.fetchDefault.title")}
      description={t("access.fetchDefault.text")}
    >
      {settings.isError && !settings.data ? (
        <Notice
          tone="err"
          role="alert"
          text={t("access.loadFailed")}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void settings.refetch();
              }}
            >
              {t("access.retry")}
            </button>
          }
        />
      ) : (
        <div className="flex flex-col" style={{ gap: 6 }}>
          <label
            htmlFor="git-fetch-default"
            style={{ fontSize: 12, fontWeight: 500 }}
          >
            {t("access.fetchDefault.label")}
          </label>
          <div className="flex items-center" style={{ gap: 8 }}>
            <div style={{ width: 240, maxWidth: "100%" }}>
              <Select
                id="git-fetch-default"
                placeholder={t("access.fetchDefault.label")}
                value={String(current)}
                options={options}
                isDisabled={settings.isPending || update.isPending}
                onValueChange={(value) => {
                  update.mutate(
                    { git_fetch_interval_s: Number(value) },
                    {
                      onSuccess: () => {
                        toast.success(t("access.fetchDefault.saved"));
                      },
                    },
                  );
                }}
              />
            </div>
            {(settings.isPending || update.isPending) && <Spinner size="sm" />}
          </div>
          {update.isError && (
            <Notice
              tone="err"
              role="alert"
              text={t("access.fetchDefault.failed")}
            />
          )}
        </div>
      )}
    </AccessCard>
  );
};
