import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowRight,
  FolderPlus,
  GraduationCap,
  History,
} from "lucide-react";
import { useSetupStatus } from "@entities/setup";
import {
  DEFAULT_FOLDER_NAME,
  baseName,
  findCheck,
  isAbsoluteHostPath,
  joinPath,
  useHostBrowser,
  useSetupFlow,
} from "@features/first-run-setup";
import { Spinner } from "@shared/ui/Spinner";
import { ComposeNotice } from "./ComposeNotice";
import { DockerNotice } from "./DockerNotice";
import { FolderBrowser } from "./FolderBrowser";
import { LanguageSwitch } from "./LanguageSwitch";
import { MachineCard } from "./MachineCard";
import { PathField } from "./PathField";
import { RestartingScreen } from "./RestartingScreen";

/**
 * Экран первоначальной настройки — всё, что видит пользователь, пока продукт не
 * умеет сохранять его работы.
 *
 * Вопрос здесь ровно один: где на вашей машине держать файлы. Одна папка вместо
 * трёх переменных окружения — намеренно: каждая развилка в установке это место,
 * где можно ошибиться, а разложить внутри подкаталоги приложение умеет само.
 *
 * Папку выбирают МЫШКОЙ, хотя интерфейс живёт в контейнере и файловой системы
 * хоста не видит: обзор идёт через докер (см. FolderBrowser). Печатать путь
 * вслепую тоже можно, но это запасной путь, а не основной.
 *
 * Раскладка держится в один экран без прокрутки страницы: человек ещё не начал
 * работать и не знает, что ниже есть что-то важное, — значит и не пойдёт туда
 * смотреть. Прокручивается только список папок внутри своей рамки.
 */
export const SetupPage = () => {
  const { t } = useTranslation("setup");
  const { data: status, refetch, isFetching } = useSetupStatus();
  const browser = useHostBrowser();
  const flow = useSetupFlow();
  const [pendingFolder, setPendingFolder] = useState<string | null>(null);
  // Пусто — довериться автоопределению каталога шрифтов.
  const [fontsPath, setFontsPath] = useState("");
  // Скачать движок LaTeX сразу после настройки; выключается в карточке машины.
  const [prefetchTex, setPrefetchTex] = useState(true);

  const dockerCheck = findCheck(status, "docker");
  const dockerDown = dockerCheck !== undefined && dockerCheck.severity !== "ok";
  const composeProject = status?.compose_project ?? null;

  // Применить мы можем не всегда, и мешают этому две РАЗНЫЕ вещи. Без доступа к
  // сокету пересоздать себя нельзя физически. В compose-установке — можно, но
  // не нужно: файл и `.env` останутся прежними, и первый же
  // `docker compose up -d` вернёт старую конфигурацию, а человек решит, что
  // приложение забыло его папку.
  const canApply = !dockerDown && composeProject === null;

  useEffect(() => {
    // Пользователь пошёл запускать Docker Desktop и вернулся во вкладку —
    // перепроверяем сами, а не заставляем его перезагружать страницу.
    if (!dockerDown) return;
    const onFocus = () => {
      void refetch();
    };
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
    };
  }, [dockerDown, refetch]);

  if (flow.status === "restarting" || flow.status === "done") {
    return <RestartingScreen target={pendingFolder ?? browser.path} />;
  }

  const probe = browser.probe;
  // Зонд не отработал (докер не ответил, монтирование отклонено) — про папку мы
  // НЕ ЗНАЕМ НИЧЕГО, и применять её нельзя: это не «пустая папка», это «мы не
  // смотрели». Раньше кнопка в этом состоянии была активна.
  const probeFailed = probe !== null && probe.status !== "ok";
  const exists = probe?.status === "ok" && probe.exists;
  // Существует, но писать в неё нельзя — с такой папки обзор как раз и
  // начинается (`C:/Users` под Windows). Выбрать её значило бы получить
  // установку, которая поднялась, но не может сохранить ни строчки.
  const readOnly = exists && !probe.writable;
  // Каталог данных прежней установки: применение его ПОДКЛЮЧИТ, а не затрёт.
  const previousInstall = exists && probe.looks_like_install;
  // «Завести здесь папку» — предложение, а не требование: класть работы прямо
  // в домашний каталог никто не запрещает.
  const suggested = joinPath(browser.path, DEFAULT_FOLDER_NAME);
  const alreadyHasSuggested =
    probe?.entries.some(
      (entry) => entry.is_dir && entry.name === DEFAULT_FOLDER_NAME,
    ) ?? false;
  const readyToApply =
    canApply &&
    isAbsoluteHostPath(browser.path) &&
    !browser.isLoading &&
    !probeFailed &&
    !readOnly;

  const apply = (target: string) => {
    setPendingFolder(target);
    flow.apply(target, fontsPath.trim() || null, prefetchTex);
  };

  return (
    <div className="setup-screen">
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          width: "100%",
          maxWidth: 1180,
          margin: "0 auto",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 42,
            height: 42,
            borderRadius: 12,
            background: "var(--c-info-soft)",
            border: "1px solid var(--c-info)",
            flexShrink: 0,
          }}
        >
          <GraduationCap size={21} style={{ color: "var(--c-info)" }} />
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
            <h1 style={{ margin: 0, fontSize: 19, fontWeight: 650 }}>
              {t("brand.name")}
            </h1>
            {status && status.app_version !== "" && (
              <span className="dim" style={{ fontSize: 11 }}>
                {t("brand.version", { version: status.app_version })}
              </span>
            )}
          </div>
          <p className="dim" style={{ margin: "2px 0 0", fontSize: 12.5 }}>
            {t("brand.tagline")}
          </p>
        </div>
        {/* Язык угадан по локали браузера. Промах правим здесь: настройки
            приложения до окончания установки недоступны. */}
        <div style={{ marginLeft: "auto" }}>
          <LanguageSwitch />
        </div>
      </header>

      <div className="setup-body">
        <section className="setup-card">
          <h2 style={{ margin: "0 0 3px", fontSize: 15, fontWeight: 600 }}>
            {t("folder.title")}
          </h2>
          <p className="dim" style={{ margin: "0 0 12px", fontSize: 12.5 }}>
            {t("folder.subtitle")}
          </p>

          <FolderBrowser
            path={browser.path}
            probe={probe}
            isLoading={browser.isLoading}
            onNavigate={browser.goTo}
          />

          <PathField
            value={browser.path}
            isRelative={browser.isRelative}
            onChange={browser.goTo}
          />

          {previousInstall && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 10,
                padding: "8px 10px",
                borderRadius: 8,
                background: "var(--c-ok-soft)",
                border: "1px solid var(--c-ok)",
                fontSize: 12.5,
              }}
            >
              <History
                size={14}
                style={{ color: "var(--c-ok)", flexShrink: 0 }}
              />
              <span>{t("folder.previousInstall")}</span>
            </div>
          )}

          {readOnly && (
            <div
              role="alert"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 10,
                padding: "8px 10px",
                borderRadius: 8,
                background: "var(--c-warn-soft)",
                border: "1px solid var(--c-warn)",
                fontSize: 12.5,
              }}
            >
              <AlertTriangle
                size={14}
                style={{ color: "var(--c-warn)", flexShrink: 0 }}
              />
              <span>{t("folder.readOnly")}</span>
            </div>
          )}

          {canApply && (
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              {!alreadyHasSuggested && (
                <button
                  type="button"
                  className="btn"
                  disabled={flow.isBusy || !readyToApply}
                  onClick={() => {
                    apply(suggested);
                  }}
                  title={suggested}
                >
                  <FolderPlus size={14} />
                  {t("apply.createHere", { name: DEFAULT_FOLDER_NAME })}
                </button>
              )}
              <button
                type="button"
                className="btn primary"
                disabled={flow.isBusy || !readyToApply}
                onClick={() => {
                  apply(browser.path);
                }}
                style={{ flex: 1, justifyContent: "center" }}
              >
                {flow.status === "applying" ? <Spinner size="sm" /> : null}
                {previousInstall
                  ? t("apply.reconnect", { name: baseName(browser.path) })
                  : exists
                    ? t("apply.useThis", { name: baseName(browser.path) })
                    : t("apply.createAndUse", { name: baseName(browser.path) })}
                <ArrowRight size={15} />
              </button>
            </div>
          )}

          {flow.errorCode && flow.status === "failed" && (
            <div
              role="alert"
              style={{
                marginTop: 12,
                padding: "9px 11px",
                borderRadius: 8,
                background: "var(--c-err-soft)",
                border: "1px solid var(--c-err)",
                fontSize: 12.5,
                color: "var(--c-err)",
              }}
            >
              {t(`error.${flow.errorCode}`, {
                defaultValue: t("error.unknown"),
              })}
            </div>
          )}
        </section>

        {/* Правая колонка: то, что помогает решиться, но решения не требует.
            Когда докер недоступен, её место занимает объяснение — без него
            выбирать папку всё равно бессмысленно. */}
        <aside className="setup-side">
          {dockerDown ? (
            <DockerNotice
              code={dockerCheck.code}
              socketGid={dockerCheck.context.socket_gid}
              hostPath={browser.path}
              isRechecking={isFetching}
              onRecheck={() => {
                void refetch();
              }}
            />
          ) : (
            <MachineCard
              probe={probe}
              fontsPath={fontsPath}
              onFontsPathChange={setFontsPath}
              prefetchTex={prefetchTex}
              onPrefetchTexChange={setPrefetchTex}
            />
          )}

          {composeProject !== null && !dockerDown && (
            <ComposeNotice project={composeProject} path={browser.path} />
          )}
        </aside>
      </div>
    </div>
  );
};
