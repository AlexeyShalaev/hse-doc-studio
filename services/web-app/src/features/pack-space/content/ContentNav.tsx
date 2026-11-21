import { useState } from "react";
import {
  Braces,
  CalendarClock,
  ClipboardList,
  FileText,
  FolderTree,
  Languages,
  ListChecks,
  PenLine,
  Search,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { ContentPart } from "./contract";
import type { ContentRoute } from "./route";
import { useContentData, type ContentData } from "./useContentData";
import { useContentNav } from "./useContentNav";
import { useContentRoute } from "./useContentRoute";
import { useSpacePhone } from "../shell/phoneContext";
import "./space-content.css";

// Левая навигация «Что редактируем» (pack-studio-ux.md, 5.5): документы списком, дальше разделы
// версии, внизу «Все файлы». Длинный список не вытесняет разделы: девять и больше документов
// показывают первые шесть и открытый, остальные за «Ещё N»; раскрытый список листается внутри
// своего блока, разделы под ним всегда на виду. Когда документов больше десяти, над списком
// появляется поиск.

const SEARCH_FROM = 10;
const COLLAPSED = 6;
// Свёртка нужна, когда она прячет хотя бы три документа: «Ещё 1» только мешает.
const COLLAPSE_FROM = 9;

const PARTS: { part: ContentPart; icon: LucideIcon }[] = [
  { part: "fields", icon: Braces },
  { part: "forms", icon: ClipboardList },
  { part: "deadlines", icon: CalendarClock },
  { part: "signatures", icon: PenLine },
  { part: "languages", icon: Languages },
  { part: "rules", icon: ListChecks },
];

type Props = {
  /** Префикс `data-testid`: навигация рисуется и слотом, и свёрнутой полосой телефона. */
  testId?: string;
};

export const ContentNavView = ({
  data,
  route,
  testId = "ct",
}: Props & { data: ContentData; route: ContentRoute }) => {
  const { t } = useTranslation("packSpace");
  const nav = useContentNav();
  // На телефоне список это страница первого уровня: переход к документу ложится в историю, и
  // «назад» браузера возвращает к списку. На широком экране документы листают заменой записи.
  const replace = !useSpacePhone();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const needle = query.trim().toLowerCase();
  const activeDoc = route.kind === "document" ? route.docId : null;
  const matching = needle
    ? data.docs.filter(
        (doc) =>
          doc.name.toLowerCase().includes(needle) ||
          doc.id.toLowerCase().includes(needle),
      )
    : data.docs;
  // «Ещё N» не прячет документ, который открыт: он остаётся на своём месте в порядке списка.
  const collapsible = !needle && matching.length >= COLLAPSE_FROM;
  const docs =
    collapsible && !expanded
      ? matching.filter(
          (doc, index) => index < COLLAPSED || doc.id === activeDoc,
        )
      : matching;
  const hidden = matching.length - docs.length;
  const activePart = route.kind === "part" ? route.part : null;
  const count = (key: ContentPart) => {
    const value = data.counts[key];
    return value === undefined ? null : (
      <span className="sp-ct-count">{value}</span>
    );
  };

  return (
    <nav
      className="sp-ct-nav"
      aria-label={t("content.nav.label")}
      data-testid={`${testId}-nav`}
    >
      <div className="sp-ct-kicker">{t("content.nav.label")}</div>
      {/* Заголовок списка ведёт в «Состав документов»: добавить, убрать, переставить документы. */}
      <Link
        replace={replace}
        to={nav.partHref("documents")}
        className={clsx(
          "sp-ct-item",
          (activeDoc !== null || activePart === "documents") && "on",
        )}
        aria-current={activePart === "documents" ? "page" : undefined}
        title={t("content.nav.documentsHint")}
        data-testid={`${testId}-part-documents`}
        onClick={nav.guardClick}
      >
        <FileText size="0.9375rem" aria-hidden="true" />
        <span className="sp-ct-label">{t("content.nav.documents")}</span>
        {count("documents")}
      </Link>
      {data.docs.length === 0 ? (
        <p className="sp-ct-empty">{t("content.nav.noDocuments")}</p>
      ) : (
        <>
          {data.docs.length > SEARCH_FROM && (
            <label className="sp-ct-search">
              <Search size="0.8125rem" aria-hidden="true" />
              <input
                type="search"
                className="input"
                value={query}
                placeholder={t("content.nav.search")}
                aria-label={t("content.nav.search")}
                onChange={(event) => {
                  setQuery(event.target.value);
                }}
                data-testid={`${testId}-search`}
              />
            </label>
          )}
          <ul className="sp-ct-docs">
            {docs.map((doc, index) => (
              <li
                key={doc.id}
                data-group-start={
                  index > 0 && doc.group !== docs[index - 1]?.group
                    ? ""
                    : undefined
                }
              >
                <Link
                  replace={replace}
                  to={nav.documentHref(doc.id)}
                  className={clsx("sp-ct-sub", doc.id === activeDoc && "on")}
                  aria-current={doc.id === activeDoc ? "page" : undefined}
                  title={doc.name}
                  data-testid={`${testId}-doc-${doc.id}`}
                  onClick={nav.guardClick}
                >
                  {doc.name}
                </Link>
              </li>
            ))}
            {docs.length === 0 && (
              <li className="sp-ct-empty">{t("content.nav.searchEmpty")}</li>
            )}
          </ul>
          {collapsible && (
            <button
              type="button"
              className="sp-ct-more"
              aria-expanded={expanded}
              data-testid={`${testId}-more`}
              onClick={() => {
                setExpanded(!expanded);
              }}
            >
              {expanded
                ? t("content.nav.less")
                : t("content.nav.more", { count: hidden })}
            </button>
          )}
        </>
      )}
      {PARTS.map(({ part, icon: Icon }) => (
        <Link
          key={part}
          replace={replace}
          to={nav.partHref(part)}
          className={clsx("sp-ct-item", part === activePart && "on")}
          aria-current={part === activePart ? "page" : undefined}
          data-testid={`${testId}-part-${part}`}
          onClick={nav.guardClick}
        >
          <Icon size="0.9375rem" aria-hidden="true" />
          <span className="sp-ct-label">{t(`content.nav.${part}`)}</span>
          {count(part)}
        </Link>
      ))}
      <hr className="sp-ct-rule" />
      <Link
        replace={replace}
        to={nav.partHref("files")}
        className={clsx("sp-ct-item", activePart === "files" && "on")}
        aria-current={activePart === "files" ? "page" : undefined}
        data-testid={`${testId}-part-files`}
        onClick={nav.guardClick}
      >
        <FolderTree size="0.9375rem" aria-hidden="true" />
        <span className="sp-ct-label">{t("content.nav.files")}</span>
        <span className="sp-ct-hint">{t("content.nav.filesHint")}</span>
      </Link>
    </nav>
  );
};

/** Слот `nav.content`. */
const ContentNav = () => {
  const data = useContentData();
  const route = useContentRoute(data);
  return <ContentNavView data={data} route={route} />;
};

export default ContentNav;
