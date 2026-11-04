import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  BookOpen,
  CircleHelp,
  Compass,
  ExternalLink,
  FlaskConical,
} from "lucide-react";
import { helpApi, openHelp } from "@entities/help";
import { useThemeStore } from "@shared/lib";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { useOnboardingStore } from "../model/onboardingStore";
import { DEMO_PATH } from "../lib/paths";

const itemStyle = {
  width: "100%",
  justifyContent: "flex-start",
  alignItems: "flex-start",
  padding: "8px 10px",
  gap: 10,
  textAlign: "left",
} as const;

/** Меню «Справка» в заголовке: знакомство заново и демо-проект. */
export const HelpMenu = () => {
  const { t } = useTranslation("onboarding");
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const start = useOnboardingStore((s) => s.start);
  const { t: tHelp } = useTranslation("help");
  const lang = useThemeStore((s) => s.lang);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="icon-btn tt"
          data-tt={t("help.button")}
          aria-label={t("help.button")}
          data-tour="titlebar-help"
          data-testid="help-menu-trigger"
          style={{ width: "2rem", height: "2rem" }}
        >
          <CircleHelp size="1rem" />
        </button>
      </PopoverTrigger>
      <PopoverContent width={280} aria-label={t("help.title")}>
        <div className="flex flex-col" style={{ padding: "0.375rem" }}>
          {/* Пользовательская справка (features/help-center): статья текущего экрана и весь сайт. */}
          <button
            type="button"
            className="row-btn"
            style={itemStyle}
            data-testid="help-menu-screen"
            onClick={() => {
              setOpen(false);
              openHelp();
            }}
          >
            <BookOpen
              size="0.9375rem"
              style={{ marginTop: "0.125rem", flexShrink: 0 }}
            />
            <span className="flex flex-col" style={{ gap: "0.125rem" }}>
              <span style={{ color: "var(--fg-0)" }}>{tHelp("command")}</span>
              <span className="dim" style={{ fontSize: "0.71875rem" }}>
                {tHelp("menuScreenHint")}
              </span>
            </span>
          </button>
          <a
            className="row-btn"
            style={itemStyle}
            href={helpApi.siteUrl(lang)}
            target="_blank"
            rel="noreferrer"
            data-testid="help-menu-site"
            onClick={() => {
              setOpen(false);
            }}
          >
            <ExternalLink
              size="0.9375rem"
              style={{ marginTop: "0.125rem", flexShrink: 0 }}
            />
            <span className="flex flex-col" style={{ gap: "0.125rem" }}>
              <span style={{ color: "var(--fg-0)" }}>{tHelp("openSite")}</span>
              <span className="dim" style={{ fontSize: "0.71875rem" }}>
                {tHelp("menuSiteHint")}
              </span>
            </span>
          </a>
          <button
            type="button"
            className="row-btn"
            style={itemStyle}
            data-testid="help-menu-tour"
            onClick={() => {
              setOpen(false);
              start("manual");
            }}
          >
            <Compass
              size="0.9375rem"
              style={{ marginTop: "0.125rem", flexShrink: 0 }}
            />
            <span className="flex flex-col" style={{ gap: "0.125rem" }}>
              <span style={{ color: "var(--fg-0)" }}>{t("help.tour")}</span>
              <span className="dim" style={{ fontSize: "0.71875rem" }}>
                {t("help.tourHint")}
              </span>
            </span>
          </button>
          <button
            type="button"
            className="row-btn"
            style={itemStyle}
            data-testid="help-menu-demo"
            onClick={() => {
              setOpen(false);
              void navigate(DEMO_PATH);
            }}
          >
            <FlaskConical
              size="0.9375rem"
              style={{ marginTop: "0.125rem", flexShrink: 0 }}
            />
            <span className="flex flex-col" style={{ gap: "0.125rem" }}>
              <span style={{ color: "var(--fg-0)" }}>{t("help.demo")}</span>
              <span className="dim" style={{ fontSize: "0.71875rem" }}>
                {t("help.demoHint")}
              </span>
            </span>
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
};
