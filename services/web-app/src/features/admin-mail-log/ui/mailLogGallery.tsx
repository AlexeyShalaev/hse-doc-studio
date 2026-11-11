import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { useListQueryState } from "@shared/lib";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { MAIL_LOG_LIST, type MailLogListState } from "../api/mailLogQueries";
import type {
  MailLogDetail,
  MailLogEntry,
  MailLogPage,
  MailLogSummary,
} from "../api/schemas";
import { ensureAdminMailLocales } from "../lib/locales";
import {
  MAIL_LOG_DETAILS,
  MAIL_LOG_MISSING_ID,
  MAIL_LOG_PAGES,
  MAIL_LOG_RECORDS,
  MAIL_LOG_SUMMARIES,
  MAIL_NOW,
  makeMailLogDetail,
  type MailLogPageState,
  type MailLogSummaryState,
} from "../testing/fixtures";
import { MailLog, MAIL_PARAM } from "./MailLog";
import { MailLogCardView, type MailLogCardState } from "./MailLogCardView";
import { MailLogView } from "./MailLogView";

// Галерея «Админка: письма» (docs/design/mail-log.md, 4.4), список (срез W2): состояния на
// эталонах сервера и своих страницах MAIL_LOG_PAGES и сводках MAIL_LOG_SUMMARIES, телефон и живые
// записи на демо-мире. Время постоянное (MAIL_NOW), чтобы «сегодня» и «вчера» не плыли.
// Карточка письма (срез W3): та же панель на месте, без затемнения; живые записи открывают её
// поверх раздела по `?mail=`.

const NOW = Date.parse(MAIL_NOW);
const PAGE_W = 1080;
const PHONE = 390;
/** Ширина панели карточки на широком экране (45rem). */
const CARD_W = 720;
const noop = () => undefined;

/** Словари админки грузятся вместе с её чанком; галерея ждёт их сама. */
const Ready = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void ensureAdminMailLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);
  return ready ? <>{children}</> : null;
};

const entry = (
  id: string,
  title: string,
  render: () => ReactNode,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: PAGE_W,
  render: () => <Ready>{render()}</Ready>,
  ...extra,
});

const live = (scenario: string) => ({ scenario });

type ListDemoProps = {
  page?: MailLogPageState;
  summary?: MailLogSummaryState | null;
  status?: "ready" | "loading" | "error";
  /** Показать вид с выбранными условиями: итог и (или) поиск. */
  filtered?: { status?: readonly string[]; q?: string };
  /** Следующая страница не загрузилась. */
  failedMore?: boolean;
};

/** Список на постоянных данных; состояние фильтров живое (адрес галереи), кроме заданного. */
const ListDemo = ({
  page = "mixed",
  summary = "normal",
  status = "ready",
  filtered,
  failedMore = false,
}: ListDemoProps) => {
  const own = useListQueryState(MAIL_LOG_LIST);
  const state: MailLogListState = filtered
    ? {
        ...own,
        q: filtered.q ?? own.q,
        filters: {
          ...own.filters,
          status: filtered.status ?? own.filters.status,
        },
        filter: (name) =>
          name === "status"
            ? (filtered.status?.[0] ?? own.filter(name))
            : own.filter(name),
        isFiltered: true,
        searchOnly: filtered.status ? "" : (filtered.q ?? ""),
        activeFilterCount: 1,
      }
    : own;
  const data: MailLogPage = MAIL_LOG_PAGES[page];
  const rows = status === "ready" ? data.items : [];
  const sum: MailLogSummary | null =
    summary === null ? null : MAIL_LOG_SUMMARIES[summary];
  return (
    <MailLogView
      state={state}
      rows={rows}
      loading={status === "loading"}
      failed={status === "error"}
      failedMore={failedMore}
      pagination={{
        mode: "cursor",
        shown: rows.length,
        hasMore: status === "ready" && data.next_cursor !== null,
        onLoadMore: noop,
        loading: false,
        totalEstimate: data.total_estimate,
      }}
      summary={sum}
      now={NOW}
      selectedId={null}
      onOpen={noop}
      onRefresh={noop}
      onRetry={noop}
    />
  );
};

const list = (props: ListDemoProps = {}) => <ListDemo {...props} />;

type CardDemoProps = {
  detail?: MailLogDetail | null;
  /** Строка списка: шапка и сведения, пока карточка грузится. */
  row?: MailLogEntry | null;
  state?: MailLogCardState;
  phone?: boolean;
};

/** Карточка на постоянных данных: панель справа или шторка, нарисованная на месте. */
const CardDemo = ({
  detail = null,
  row = null,
  state = "ready",
  phone = false,
}: CardDemoProps) => (
  <div
    className="ml-card"
    data-form={phone ? "sheet" : "drawer"}
    data-inline="true"
    data-testid="mail-card"
  >
    <MailLogCardView
      entry={detail?.entry ?? row}
      detail={state === "ready" ? detail : null}
      state={state}
      now={NOW}
      onRetry={noop}
      onClose={noop}
      onShowRecipient={noop}
      onShowProject={noop}
    />
  </div>
);

const D = MAIL_LOG_DETAILS;
const R = MAIL_LOG_RECORDS;

const card = (
  id: string,
  title: string,
  props: CardDemoProps,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry =>
  entry(id, title, () => <CardDemo {...props} />, {
    frame: "plain",
    width: props.phone ? PHONE : CARD_W,
    ...extra,
  });

/** Раздел с открытой карточкой: `?mail=<id>` ставится при открытии записи. */
const LiveCard = ({ id }: { id: number }) => {
  const [, setParams] = useSearchParams();
  useEffect(() => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(MAIL_PARAM, String(id));
        return next;
      },
      { replace: true },
    );
  }, [id, setParams]);
  return <MailLog />;
};

/** Список «Письма» (4.4): состояния, телефон и живой раздел по сценариям демо-мира. */
export const getAdminMailLogGallery = (): GalleryGroup[] => [
  {
    id: "admin-mail-list",
    title: "Админка: письма, список",
    description:
      "Шапка со сроком хранения, плашка «Почта не настроена», полоса за сутки с подсказкой по классу сбоя, фильтры в адресе и таблица по курсору. Строка открывает карточку письма (?mail=), её рисует срез W3.",
    entries: [
      entry("mail_list_day", "Обычный день: все виды и итоги", () => list(), {
        note: "«Не ушло» в полосе красным: клик ставит фильтр «Не ушло» за сутки. У строки «Вызвал» человек, «Запрос без входа» или «Фоновая задача».",
      }),
      entry(
        "mail_list_more",
        "Есть следующая страница",
        () => list({ page: "day" }),
        { note: "«Показать ещё» по next_cursor, «из N» по оценке сервера." },
      ),
      entry(
        "mail_list_failed_filter",
        "Фильтр «Не ушло»",
        () =>
          list({ page: "filtered_failed", filtered: { status: ["failed"] } }),
        { note: "С фильтром сервер не даёт оценку числа: «из N» нет." },
      ),
      entry(
        "mail_list_smtp_off",
        "Почта не настроена",
        () => list({ page: "smtp_off", summary: "smtp_off" }),
        {
          note: "Плашка со ссылкой «Настроить почту» на блок «Почта (SMTP)»; строки «Не отправлялось, почта не настроена».",
        },
      ),
      entry(
        "mail_list_auth_failure",
        "Сбой входа на SMTP",
        () => list({ page: "auth_failure", summary: "auth_failure" }),
        {
          note: "Под полосой подсказка класса auth со ссылкой на настройки почты.",
        },
      ),
      entry("mail_list_long", "Длинные адреса и темы", () =>
        list({ page: "long" }),
      ),
      entry("mail_list_empty", "Писем пока не было", () =>
        list({ page: "empty", summary: "quiet" }),
      ),
      entry(
        "mail_list_nothing_found",
        "Ничего не нашлось",
        () =>
          list({
            page: "nothing_found",
            filtered: { q: "nobody@example.org" },
          }),
        { note: "«Сбросить фильтры» возвращает весь журнал." },
      ),
      entry("mail_list_loading", "Загрузка", () =>
        list({ status: "loading", summary: null }),
      ),
      entry("mail_list_error", "Журнал не загрузился", () =>
        list({ status: "error", summary: null }),
      ),
      entry("mail_list_more_failed", "Следующая страница не загрузилась", () =>
        list({ page: "day", failedMore: true }),
      ),
      entry("mail_list_phone", "Телефон: обычный день", () => list(), {
        width: PHONE,
        note: "Таблица становится карточками: вид и тема, метка итога, адрес и время.",
      }),
      entry(
        "mail_list_phone_smtp_off",
        "Телефон: почта не настроена",
        () => list({ page: "smtp_off", summary: "smtp_off" }),
        { width: PHONE },
      ),
    ],
  },
  {
    id: "admin-mail-live",
    title: "Админка: письма, живые",
    description:
      "Раздел целиком на демо-мире: фильтры, поиск и «Показать ещё» ходят в моки журнала. Тестовое письмо из «Почта (SMTP)» дописывает строку.",
    entries: [
      entry("mail_live_day", "Обычный день", () => <MailLog />, {
        ...live("admin_ready"),
      }),
      entry("mail_live_smtp_off", "Почта не настроена", () => <MailLog />, {
        ...live("admin_sso"),
      }),
      entry(
        "mail_live_auth",
        "SMTP-сервер отклоняет вход",
        () => <MailLog />,
        live("ops_services_degraded"),
      ),
      entry("mail_live_empty", "Чистая установка", () => <MailLog />, {
        ...live("ops_fresh"),
      }),
      entry(
        "mail_live_scale",
        "Большой журнал: 1200 писем",
        () => <MailLog />,
        live("admin_scale"),
      ),
    ],
  },
  {
    id: "admin-mail-card",
    title: "Админка: письма, карточка",
    description:
      "Карточка по ?mail=<id>: вид и тема, итог, сведения, письмо в песочнице (iframe sandbox) с пометками и «Что можно сделать». В разделе это панель справа, на телефоне шторка снизу; здесь та же панель нарисована на месте.",
    entries: [
      card(
        "mail_card_token_link",
        "Сброс пароля: ссылка скрыта",
        { detail: D.token_link },
        {
          note: "Пометка «Ссылка скрыта»: кнопка в письме без адреса, вместо ссылки «[ссылка скрыта]». Message-ID копируется.",
        },
      ),
      card(
        "mail_card_page_link",
        "Уведомление маршрута: адрес страницы",
        { detail: D.page_link },
        { note: "У писем без токена на месте ссылки путь страницы текстом." },
      ),
      card(
        "mail_card_failed_note",
        "Не ушло: 550 и сообщение приглашающего",
        { detail: D.failed_with_note },
        {
          note: "Итог: класс сбоя и ответ SMTP с кнопкой «Копировать»; пометка «Сообщение отправителя не хранится».",
        },
      ),
      card(
        "mail_card_failed_auth",
        "Не ушло: SMTP-сервер отклонил вход, фоновая задача (EN)",
        { detail: D.failed_auth_system },
        {
          note: "Ссылка «Открыть настройки почты» в итоге и первая строка «Что можно сделать».",
        },
      ),
      card("mail_card_rerendered", "Перерисовано по текущему шаблону", {
        detail: D.rerendered,
      }),
      card(
        "mail_card_template_gone",
        "Вид письма удалён",
        { detail: D.template_gone },
        { note: "Превью нет, только сведения и объяснение." },
      ),
      card("mail_card_suppressed", "Не отправлялось: почта не подтверждена", {
        detail: D.suppressed,
      }),
      card("mail_card_suppressed_blocked", "Не отправлялось: вход закрыт", {
        detail: D.suppressed_blocked,
      }),
      card("mail_card_not_sent", "Не отправлялось: почта не настроена", {
        detail: D.not_sent,
      }),
      card("mail_card_anonymous", "Регистрация: запрос без входа", {
        detail: makeMailLogDetail(R.anonymous),
      }),
      card("mail_card_system", "Автонапоминание маршрута: фоновая задача", {
        detail: makeMailLogDetail(R.system_task),
      }),
      card(
        "mail_card_project_gone",
        "Проект и вызвавший удалены",
        { detail: D.project_gone },
        {
          note: "«Проект удалён» без ссылки, «Пользователь удалён» в «Вызвал».",
        },
      ),
      card("mail_card_long", "Длинные адрес, тема и имена", {
        detail: D.long,
      }),
      card(
        "mail_card_loading_row",
        "Грузится: шапка из строки списка",
        { row: D.token_link.entry, state: "loading" },
        {
          note: "Строка уже на странице списка: сведения видны сразу, превью догружается.",
        },
      ),
      card("mail_card_loading", "Грузится: письма нет на странице", {
        state: "loading",
      }),
      card("mail_card_error", "Карточка не загрузилась", { state: "error" }),
      card(
        "mail_card_not_found",
        "Письмо не найдено",
        { state: "not_found" },
        { note: "Сервер ответил 404: запись удалена по сроку хранения." },
      ),
      card("mail_card_phone", "Телефон: сброс пароля", {
        detail: D.token_link,
        phone: true,
      }),
      card("mail_card_phone_failed", "Телефон: не ушло", {
        detail: D.failed_with_note,
        phone: true,
      }),
    ],
  },
  {
    id: "admin-mail-card-live",
    title: "Админка: письма, карточка, живые",
    description:
      "Раздел на демо-мире с открытой карточкой: панель поверх списка, закрытие убирает ?mail, «Показать все письма этому адресату» ставит фильтр.",
    entries: [
      entry(
        "mail_card_live_token",
        "Открыта карточка: сброс пароля",
        () => <LiveCard id={R.token_link.entry.id} />,
        live("admin_ready"),
      ),
      entry(
        "mail_card_live_failed",
        "Открыта карточка: 550",
        () => <LiveCard id={R.failed_550.entry.id} />,
        live("admin_ready"),
      ),
      entry(
        "mail_card_live_missing",
        "Письмо удалено по сроку",
        () => <LiveCard id={MAIL_LOG_MISSING_ID} />,
        live("admin_ready"),
      ),
    ],
  },
];
