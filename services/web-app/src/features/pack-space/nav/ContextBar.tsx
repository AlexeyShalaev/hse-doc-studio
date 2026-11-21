import { useCallback, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { NewPackTarget } from "@features/pack-scaffold";
import { usePackStudioCommand } from "@shared/lib";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { SpaceTabs } from "../shell/DefaultParts";
import { CreateDialog } from "./CreateDialog";
import { Crumbs } from "./Crumbs";
import { VersionState } from "./VersionState";
import { WhereSheet } from "./WhereSheet";
import { useRememberVersion } from "./lastVisited";
import { useWhere } from "./useWhere";
import "./space-nav.css";

/**
 * Вторая полоса: «что смотрю» (пак, шаблон, версия с состоянием словом) и три вкладки.
 * Десктоп и планшет: три выпадающие крошки. Телефон: одна кнопка «Курсовой проект · 2026.1.3
 * [черновик]», она открывает шторку «Куда перейти»; вкладок здесь нет (они внизу). Какая из
 * двух частей видна, решает CSS по `data-phone` каркаса: так экран верен и в рамке галереи.
 */
export const ContextBar = () => {
  const { t } = useTranslation("packSpace");
  const { released, versionRef, workspace } = useSpace();
  const nav = useSpaceNav();
  const where = useWhere();
  const [sheet, setSheet] = useState(false);
  const [create, setCreate] = useState<NewPackTarget | null>(null);
  useRememberVersion();
  // Палитра команд (Cmd+K): «Перейти к: пак, шаблон, версия» открывает то же окно «Куда перейти».
  usePackStudioCommand(
    "where",
    useCallback(() => {
      setSheet(true);
    }, []),
  );

  return (
    <>
      <Crumbs where={where} onCreate={setCreate} />
      <SpaceTabs />
      <button
        type="button"
        className="sp-where"
        title={t("nav.where.title")}
        aria-haspopup="dialog"
        data-testid="sp-where"
        onClick={() => {
          setSheet(true);
        }}
      >
        <span className="sp-where-label truncate">
          {t("nav.where.place", {
            template: where.templateName,
            version: versionRef.version,
          })}
        </span>
        <VersionState released={released} />
        <ChevronDown size="0.75rem" aria-hidden="true" />
      </button>
      <WhereSheet
        open={sheet}
        onClose={() => {
          setSheet(false);
        }}
        where={where}
        onCreate={setCreate}
      />
      <CreateDialog
        workspaceId={workspace.id}
        target={create}
        onClose={() => {
          setCreate(null);
        }}
        onOpen={(ref) => {
          nav.go({ ref });
        }}
      />
    </>
  );
};
