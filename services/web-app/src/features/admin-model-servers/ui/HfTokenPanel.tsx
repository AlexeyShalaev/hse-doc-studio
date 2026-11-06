import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Badge, Button, Input, Section, SettingRow } from "@shared/ui";
import { useHfToken, useModelServerSettings } from "../api/queries";

/** Токен Hugging Face для закрытых моделей. Значение не показывается и не возвращается: только факт наличия. */
export const HfTokenPanel = () => {
  const { t } = useTranslation("adminModelServers");
  const settings = useModelServerSettings();
  const { save, clear } = useHfToken();
  const [value, setValue] = useState("");
  const isSet = settings.data?.hf_token_set ?? false;
  const failed = save.isError ? failureCode(save.error) : null;

  return (
    <Section
      title={t("hfToken.title")}
      description={t("hfToken.lead")}
      testId="ms-hf-token"
      footer={
        <div className="flex flex-wrap items-center" style={{ gap: "0.75rem" }}>
          <Button
            size="sm"
            disabled={value.trim() === "" || save.isPending}
            data-testid="ms-hf-save"
            onClick={() => {
              save.mutate(value.trim(), {
                onSuccess: () => {
                  setValue("");
                },
              });
            }}
          >
            {isSet ? t("hfToken.replace") : t("hfToken.save")}
          </Button>
          {isSet && (
            <Button
              size="sm"
              variant="ghost"
              disabled={clear.isPending}
              data-testid="ms-hf-clear"
              onClick={() => {
                clear.mutate();
              }}
            >
              {t("hfToken.remove")}
            </Button>
          )}
          {failed && (
            <span className="form-hint" role="alert">
              {t("hfToken.invalid")}
            </span>
          )}
        </div>
      }
    >
      <SettingRow
        label={t("hfToken.label")}
        hint={t("hfToken.hint")}
        htmlFor="ms-hf-input"
      >
        <div style={{ display: "grid", gap: "0.5rem" }}>
          <Badge
            variant={isSet ? "success" : "default"}
            data-testid="ms-hf-state"
          >
            {isSet ? t("hfToken.isSet") : t("hfToken.notSet")}
          </Badge>
          <Input
            id="ms-hf-input"
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            maxLength={512}
            value={value}
            placeholder="hf_..."
            onChange={(e) => {
              setValue(e.target.value);
            }}
            data-testid="ms-hf-input"
          />
        </div>
      </SettingRow>
    </Section>
  );
};
