import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { Spinner } from "@shared/ui";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { CasesPart } from "./CasesPart";
import { ComparePart } from "./ComparePart";
import { IssuesPart } from "./IssuesPart";
import { MapPart } from "./MapPart";
import { CHECK_PARTS, readCheck, type CheckPart } from "./lib";
import "./space-check.css";

/** Словарь прежних режимов (подписи условий, виды правил, «Сравнить») подгружается вместе с частью. */
const useOldLocale = (): boolean => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    const done = () => {
      if (live) setReady(true);
    };
    loadPackOutcomeNamespace().then(done, done);
    return () => {
      live = false;
    };
  }, []);
  return ready;
};

/** Части и сравнение рядом: на телефоне левой колонки нет, поэтому разделы переключаются здесь. */
const PhoneSwitch = ({
  part,
  compare,
}: {
  part: CheckPart;
  compare: boolean;
}) => {
  const { t } = useTranslation("packSpace");
  const nav = useSpaceNav();
  return (
    <nav className="sp-ck-switch" aria-label={t("check.nav.label")}>
      {CHECK_PARTS.map((item) => (
        <Link
          key={item}
          to={nav.href({ part: item, extra: { compare: null } })}
          aria-current={!compare && part === item ? "page" : undefined}
        >
          {t(`check.nav.${item}`)}
        </Link>
      ))}
      <Link
        to={nav.href({ extra: { compare: "1" } })}
        aria-current={compare ? "page" : undefined}
      >
        {t("check.nav.compareShort")}
      </Link>
    </nav>
  );
};

/** Центр вкладки «Проверка»: заголовок с одной фразой «зачем это» и выбранная часть. */
const CheckMain = () => {
  const { t } = useTranslation("packSpace");
  const { location } = useSpace();
  const ready = useOldLocale();
  const { part, compare } = readCheck(location.search);
  const key = compare ? "compare" : part;
  return (
    <div className="sp-ck">
      <PhoneSwitch part={part} compare={compare} />
      <header className="sp-ck-head">
        <h2 className="sp-ck-title">{t(`check.${key}.title`)}</h2>
        <p className="sp-ck-lead">{t(`check.${key}.lead`)}</p>
      </header>
      {!ready ? (
        <div className="sp-ck-loading">
          <Spinner size="md" />
        </div>
      ) : compare ? (
        <ComparePart />
      ) : part === "cases" ? (
        <CasesPart />
      ) : part === "map" ? (
        <MapPart />
      ) : (
        <IssuesPart />
      )}
    </div>
  );
};

export default CheckMain;
