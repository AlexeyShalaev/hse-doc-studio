import { useMemo, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowLeft } from "lucide-react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { usePackScenarios } from "@entities/pack-studio";
import {
  OutcomeModelContext,
  parseOutcomeSearch,
  type OutcomeModel,
} from "@features/pack-outcome";
import {
  CompareMode,
  formatSide,
  type CompareSide,
} from "@features/pack-outcome/check";
import { useIsPhoneWidth } from "@shared/lib";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { CheckChangeEnv } from "./ChangeEnv";
import { useCheckEnv } from "./useCheckEnv";

/**
 * Прежний режим «Сравнить» читает подписи из словаря старого экрана. Чтобы человек не видел там
 * внутренних слов, поверх него накладываются подписи `check.compare.words` (на копии словаря:
 * старый экран их не видит).
 */
const WithPlainWords = ({ children }: { children: ReactNode }) => {
  const { i18n } = useTranslation("packSpace");
  const lng = i18n.language;
  const forked = useMemo(() => {
    const clone = i18n.cloneInstance({ forkResourceStore: true });
    const words: unknown = i18n.getResource(
      lng,
      "packSpace",
      "check.compare.words",
    );
    if (words !== null && typeof words === "object") {
      clone.addResourceBundle(lng, "packOutcome", words, true, true);
    }
    return clone;
  }, [i18n, lng]);
  return <I18nextProvider i18n={forked}>{children}</I18nextProvider>;
};

/**
 * Сравнение двух ситуаций (или «основная версия против моих правок») без вкладки: открывается по
 * `?compare=1` из «Проверки», меню «Ещё» полосы «Для студента» и панели «Изменения». Внутри прежний
 * режим «Сравнить»: стороны, различия и «Почему?» считает он. Ему нужны только условия экрана и
 * стороны из адреса, поэтому модель экрана здесь собрана из адреса пространства.
 */
export const ComparePart = () => {
  const { t } = useTranslation("packSpace");
  const env = useCheckEnv();
  const { workspace, location } = useSpace();
  const nav = useSpaceNav();
  const phone = useIsPhoneWidth();
  const scenarios = usePackScenarios(
    env.workspaceId,
    env.ref.pack,
    env.ref.template,
    true,
  );

  const model = useMemo(() => {
    // В новом адресе готовый случай называется `case`, у прежнего экрана `scenario`.
    const params = new URLSearchParams(location.search);
    const id = params.get("case");
    if (id !== null) params.set("scenario", id);
    const state = parseOutcomeSearch(params);
    const base = {
      workspaceId: env.workspaceId,
      ref: env.ref,
      versionPath: env.versionPath,
      released: env.released,
      phone,
      view: "author",
      inputs: env.inputs,
      scenarios,
      workspaceKind: workspace.kind,
      url: {
        state,
        // Режим «Сравнить» пишет в адрес только стороны.
        update: (patch: {
          left?: CompareSide | null;
          right?: CompareSide | null;
        }) => {
          const extra: Record<string, string | null> = {};
          if (patch.left !== undefined) {
            extra.left = patch.left ? formatSide(patch.left) : null;
          }
          if (patch.right !== undefined) {
            extra.right = patch.right ? formatSide(patch.right) : null;
          }
          nav.go({ extra });
        },
      },
    };
    // Остальное (расчёт результата, подсветка, телефонная навигация) режиму «Сравнить» не нужно.
    return base as unknown as OutcomeModel;
  }, [env, location.search, phone, scenarios, workspace.kind, nav]);

  const back = (
    <Link
      className="btn sm"
      to={nav.href({ extra: { compare: null, left: null, right: null } })}
    >
      <ArrowLeft size="0.8125rem" aria-hidden="true" />
      {t("check.compare.back")}
    </Link>
  );
  return (
    <div className="sp-ck-stack">
      <div>{back}</div>
      <OutcomeModelContext.Provider value={model}>
        <WithPlainWords>
          <CheckChangeEnv env={env}>
            <CompareMode />
          </CheckChangeEnv>
        </WithPlainWords>
      </OutcomeModelContext.Provider>
    </div>
  );
};
