import { Link } from "react-router";
import {
  GitCompareArrows,
  ListChecks,
  Network,
  ShieldCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePackOutcomeLint } from "@entities/pack-studio";
import { countsOf } from "@entities/pack-studio/outcome/lint";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { readCheck, type CheckPart } from "./lib";
import "./space-check.css";

const ICON = {
  issues: ShieldCheck,
  cases: ListChecks,
  map: Network,
} satisfies Record<CheckPart, typeof ShieldCheck>;

/**
 * Левая колонка «Проверки»: три части и сравнение. На «Замечаниях» число ошибок и замечаний, чтобы
 * было видно, нужно ли сюда идти. Расчёт общий с центром (один запрос на двоих).
 */
const CheckNav = () => {
  const { t } = useTranslation("packSpace");
  const { workspace, versionRef, location } = useSpace();
  const nav = useSpaceNav();
  const { part, compare } = readCheck(location.search);
  const lint = usePackOutcomeLint(
    workspace.id,
    versionRef,
    { state: "work_tree" },
    true,
  );
  const counts = lint.data ? countsOf(lint.data) : null;
  const open = counts ? counts.errors + counts.warnings : 0;
  return (
    <nav className="sp-ck-nav" aria-label={t("check.nav.label")}>
      <ul>
        {(["issues", "cases", "map"] as const).map((item) => {
          const Icon = ICON[item];
          return (
            <li key={item}>
              <Link
                to={nav.href({ part: item, extra: { compare: null } })}
                aria-current={!compare && part === item ? "page" : undefined}
              >
                <Icon size="0.9375rem" aria-hidden="true" />
                <span>{t(`check.nav.${item}`)}</span>
                {item === "issues" && counts !== null && open > 0 && (
                  <span
                    className="sp-ck-badge"
                    data-tone={counts.errors > 0 ? "error" : "warn"}
                    aria-label={t("check.nav.open", { count: open })}
                  >
                    {open}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
      <hr />
      <ul>
        <li>
          <Link
            to={nav.href({ extra: { compare: "1" } })}
            aria-current={compare ? "page" : undefined}
          >
            <GitCompareArrows size="0.9375rem" aria-hidden="true" />
            <span>{t("check.nav.compare")}</span>
          </Link>
        </li>
      </ul>
    </nav>
  );
};

export default CheckNav;
