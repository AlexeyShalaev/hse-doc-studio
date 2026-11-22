import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { OutcomeElementRef, OutcomeTrace } from "@entities/pack-studio";
import { ruleKey } from "@entities/pack-studio/outcome/rules";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";

type TechnicalDetailsProps = {
  element: OutcomeElementRef;
  chain: readonly OutcomeTrace[];
};

/**
 * «Технические подробности» (свёрнуто): идентификатор элемента, файл и указатель каждого
 * правила, переходы «Открыть файл правила» и «Текст файла». Единственное место панели, где
 * есть имена файлов и идентификаторы.
 */
export const TechnicalDetails = ({ element, chain }: TechnicalDetailsProps) => {
  const { t } = useTranslation("packSpace");
  const { version } = useSpace();
  const nav = useSpaceNav();
  const seen = new Set<string>();
  const rules = chain.filter((trace) => {
    const key = ruleKey(trace.rule);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const back = nav.href();
  const toFile = (
    file: string,
    pointer: string | null,
    pane: "form" | "source",
  ) =>
    nav.href({
      tab: "content",
      file: `${version?.path ?? ""}/${file}`,
      extra: { at: pointer, pane, from: back },
    });
  return (
    <details className="sp-details-tech" data-testid="sp-tech">
      <summary>{t("details.tech.title")}</summary>
      <dl className="sp-tech-list">
        <div>
          <dt>{t("details.tech.element")}</dt>
          <dd className="mono">{`${element.section}:${element.id}`}</dd>
        </div>
        {rules.map((trace) => {
          const { rule } = trace;
          const manifest = rule.origin === "manifest" && rule.file !== null;
          return (
            <div key={trace.id} data-testid="sp-tech-rule">
              <dt>
                {t(`details.tech.kinds.${trace.kind}`, {
                  defaultValue: trace.kind,
                })}
              </dt>
              <dd className="mono">
                {manifest
                  ? `${rule.file ?? ""}${rule.pointer ?? ""}`
                  : t("details.tech.builtin", { name: rule.builtin ?? "" })}
              </dd>
              {manifest && version && (
                <dd className="sp-details-row">
                  <Link
                    className="btn sm"
                    to={toFile(rule.file ?? "", rule.pointer, "form")}
                    data-testid="sp-tech-open"
                  >
                    {t("details.tech.openFile")}
                  </Link>
                  <Link
                    className="btn sm ghost"
                    to={toFile(rule.file ?? "", rule.pointer, "source")}
                    data-testid="sp-tech-source"
                  >
                    {t("details.tech.source")}
                  </Link>
                </dd>
              )}
            </div>
          );
        })}
      </dl>
    </details>
  );
};
