import type {
  AdminInvitation,
  AdminJob,
  AdminOrgMember,
  AdminRunner,
  AdminRunnerToken,
  AdminUser,
  JobState,
  OrgRoleName,
} from "@entities/session";
import { createDemoAdminOps, type DemoAdminOps } from "./adminOps";
import {
  DIRECTORY,
  createDemoAdminOrgs,
  type DemoAdminOrgs,
  type DemoDirectoryUser,
  type DemoOrg,
} from "./adminOrgs";
import {
  RECENT_AUDIT,
  allUsers,
  type DemoAdminPeople,
  type DemoAuditArchive,
} from "./adminPeople";

// Большой мир демо (сценарий admin_scale): установка, где людей десятки тысяч.
// Нужен, чтобы оценить поиск, фильтры и листание на настоящих объёмах:
// 12 000 человек, 800 организаций, 3 000 групп, 150 раннеров, 40 000 задач,
// 2 000 приглашений и 250 000 записей журнала. Всё детерминировано: один и
// тот же мир при каждом открытии. Журнал не хранится, запись строится по id.
// Малый мир по умолчанию остаётся как был; этот файл грузится только с демо.

export const SCALE = {
  people: 12_000,
  orgs: 800,
  groups: 3_000,
  runners: 150,
  tokens: 80,
  jobs: 40_000,
  projects: 6_000,
  invitations: 2_000,
  audit: 250_000,
} as const;

/** Детерминированный генератор (mulberry32). */
const rng = (seed: number) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

type Rand = () => number;
const int = (r: Rand, min: number, max: number) =>
  min + Math.floor(r() * (max - min + 1));
const pick = <T>(r: Rand, list: readonly T[]): T => {
  const item = list[Math.floor(r() * list.length)];
  if (item === undefined) throw new Error("scale world: empty list");
  return item;
};
/** Выбор по весам: [значение, вес]. */
const weighted = <T>(r: Rand, table: readonly (readonly [T, number])[]): T => {
  const total = table.reduce((sum, [, w]) => sum + w, 0);
  let x = r() * total;
  for (const [value, w] of table) {
    x -= w;
    if (x < 0) return value;
  }
  const last = table[table.length - 1];
  if (!last) throw new Error("scale world: empty table");
  return last[0];
};
const pad = (n: number, width: number) => String(n).padStart(width, "0");

const MALE = [
  "Александр",
  "Алексей",
  "Андрей",
  "Артём",
  "Борис",
  "Вадим",
  "Владимир",
  "Глеб",
  "Григорий",
  "Даниил",
  "Денис",
  "Дмитрий",
  "Егор",
  "Иван",
  "Игорь",
  "Илья",
  "Кирилл",
  "Константин",
  "Лев",
  "Максим",
  "Марк",
  "Матвей",
  "Михаил",
  "Никита",
  "Николай",
  "Олег",
  "Павел",
  "Пётр",
  "Роман",
  "Сергей",
  "Степан",
  "Тимофей",
  "Фёдор",
  "Юрий",
  "Ярослав",
] as const;
const FEMALE = [
  "Алина",
  "Алиса",
  "Анастасия",
  "Анна",
  "Арина",
  "Валерия",
  "Вера",
  "Виктория",
  "Дарья",
  "Диана",
  "Ева",
  "Екатерина",
  "Елена",
  "Елизавета",
  "Ирина",
  "Ксения",
  "Маргарита",
  "Мария",
  "Марина",
  "Милана",
  "Надежда",
  "Наталья",
  "Ольга",
  "Полина",
  "Светлана",
  "Софья",
  "Таисия",
  "Татьяна",
  "Ульяна",
  "Юлия",
] as const;
const SURNAMES = [
  "Иванов",
  "Смирнов",
  "Кузнецов",
  "Попов",
  "Васильев",
  "Петров",
  "Соколов",
  "Михайлов",
  "Новиков",
  "Фёдоров",
  "Морозов",
  "Волков",
  "Алексеев",
  "Лебедев",
  "Семёнов",
  "Егоров",
  "Павлов",
  "Козлов",
  "Степанов",
  "Николаев",
  "Орлов",
  "Андреев",
  "Макаров",
  "Никитин",
  "Захаров",
  "Зайцев",
  "Соловьёв",
  "Борисов",
  "Яковлев",
  "Григорьев",
  "Романов",
  "Воробьёв",
  "Сергеев",
  "Кузьмин",
  "Фролов",
  "Александров",
  "Дмитриев",
  "Королёв",
  "Гусев",
  "Киселёв",
  "Ильин",
  "Максимов",
  "Поляков",
  "Сорокин",
  "Виноградов",
  "Ковалёв",
  "Белов",
  "Медведев",
  "Антонов",
  "Тарасов",
  "Жуков",
  "Баранов",
  "Филиппов",
  "Комаров",
  "Давыдов",
  "Беляев",
  "Герасимов",
  "Богданов",
  "Осипов",
  "Сидоров",
  "Матвеев",
  "Титов",
  "Марков",
  "Миронов",
  "Крылов",
  "Куликов",
  "Карпов",
  "Власов",
  "Мельников",
  "Денисов",
  "Гаврилов",
  "Тихонов",
  "Казаков",
  "Афанасьев",
  "Данилов",
  "Савельев",
  "Тимофеев",
  "Фомин",
  "Чернов",
  "Абрамов",
  "Мартынов",
  "Ефимов",
  "Федотов",
  "Щербаков",
  "Назаров",
  "Калинин",
  "Исаев",
  "Чернышёв",
  "Быков",
  "Маслов",
] as const;

const TRANSLIT: Record<string, string> = {
  а: "a",
  б: "b",
  в: "v",
  г: "g",
  д: "d",
  е: "e",
  ё: "e",
  ж: "zh",
  з: "z",
  и: "i",
  й: "y",
  к: "k",
  л: "l",
  м: "m",
  н: "n",
  о: "o",
  п: "p",
  р: "r",
  с: "s",
  т: "t",
  у: "u",
  ф: "f",
  х: "kh",
  ц: "ts",
  ч: "ch",
  ш: "sh",
  щ: "shch",
  ъ: "",
  ы: "y",
  ь: "",
  э: "e",
  ю: "yu",
  я: "ya",
};
const translit = (text: string): string =>
  text
    .toLowerCase()
    .replace(/./gu, (ch) => TRANSLIT[ch] ?? (/[a-z0-9]/.test(ch) ? ch : "-"))
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");

const femaleSurname = (surname: string): string =>
  surname.endsWith("ий") ? `${surname.slice(0, -2)}ая` : `${surname}а`;

const DAY = 86_400_000;

type Person = AdminUser;

const generatePeople = (r: Rand, now: number): Person[] => {
  const base = allUsers();
  const emails = new Set(base.map((u) => u.email));
  const out: Person[] = [...base];
  const domains = [
    "edu.hse.ru",
    "edu.hse.ru",
    "edu.hse.ru",
    "hse.ru",
    "example.org",
  ];
  for (let i = out.length; i < SCALE.people; i += 1) {
    const female = r() < 0.52;
    const first = female ? pick(r, FEMALE) : pick(r, MALE);
    const surname = pick(r, SURNAMES);
    const last = female ? femaleSurname(surname) : surname;
    const stem = `${translit(first).slice(0, 1)}.${translit(last)}`;
    const domain = pick(r, domains);
    let email = `${stem}@${domain}`;
    for (let n = 2; emails.has(email); n += 1)
      email = `${stem}${String(n)}@${domain}`;
    emails.add(email);
    const status = weighted<Person["status"]>(r, [
      ["active", 920],
      ["pending_verification", 20],
      ["pending_approval", 12],
      ["disabled", 48],
    ]);
    const createdDays = r() * 3 * 365;
    const never =
      status === "pending_verification" || status === "pending_approval";
    out.push({
      id: `u_s${pad(i, 5)}`,
      name: `${first} ${last}`,
      email,
      status,
      is_instance_admin: i % 1999 === 0 && status === "active",
      created_at: new Date(now - createdDays * DAY).toISOString(),
      last_login_at: never
        ? null
        : r() < 0.06
          ? null
          : new Date(
              now - r() * Math.min(createdDays, 120) * DAY,
            ).toISOString(),
      project_count:
        status === "active"
          ? weighted(r, [
              [0, 30],
              [1, 35],
              [2, 18],
              [3, 9],
              [5, 5],
              [9, 3],
            ])
          : 0,
    });
  }
  return out;
};

const SUBJECTS = [
  "Программная инженерия",
  "Прикладная математика",
  "Анализ данных",
  "Экономика",
  "Менеджмент",
  "Дизайн",
  "Журналистика",
  "Социология",
  "Психология",
  "История",
  "Филология",
  "Право",
  "Физика",
  "Химия",
  "Биоинформатика",
  "Компьютерная безопасность",
  "Логистика",
  "Маркетинг",
  "Финансы",
  "Политология",
  "Востоковедение",
  "Урбанистика",
  "Философия",
  "Лингвистика",
  "Медиакоммуникации",
] as const;
const ORG_KINDS = [
  "Кафедра",
  "Лаборатория",
  "Проектный семинар",
  "Курс",
  "Школа",
  "Центр",
  "Студия",
  "Департамент",
] as const;

type SeedOrg = { org: DemoOrg; weight: number };

const membersOf = (
  r: Rand,
  people: readonly Person[],
  size: number,
  now: number,
): AdminOrgMember[] => {
  // size разных людей без повторов: маленьким организациям хватает выборки
  // с отсевом, большим нужна перестановка (иначе отсев крутится долго).
  const count = Math.min(size, people.length);
  const chosen: number[] = [];
  if (count * 4 < people.length) {
    const seen = new Set<number>();
    while (chosen.length < count) {
      const k = Math.floor(r() * people.length);
      if (!seen.has(k)) {
        seen.add(k);
        chosen.push(k);
      }
    }
  } else {
    const pool = people.map((_, i) => i);
    for (let i = 0; i < count; i += 1) {
      const j = i + Math.floor(r() * (pool.length - i));
      const a = pool[i] ?? 0;
      const b = pool[j] ?? 0;
      pool[i] = b;
      pool[j] = a;
      chosen.push(b);
    }
  }
  const out: AdminOrgMember[] = [];
  for (const [i, b] of chosen.entries()) {
    const person = people[b];
    if (!person) continue;
    const role: OrgRoleName =
      i === 0 || (i < 3 && r() < 0.3)
        ? "owner"
        : i < 3 + Math.ceil(count / 40)
          ? "admin"
          : "member";
    out.push({
      user_id: person.id,
      name: person.name,
      email: person.email,
      role,
      joined_at: new Date(now - r() * 700 * DAY)
        .toISOString()
        .replace(/\.\d+Z$/, "Z"),
    });
  }
  return out;
};

const generateOrgs = (
  r: Rand,
  people: readonly Person[],
  now: number,
): DemoAdminOrgs => {
  const base = createDemoAdminOrgs("default");
  const active = people.filter((p) => p.status === "active");
  const directory: DemoDirectoryUser[] = [
    ...DIRECTORY.map((u) => ({ ...u })),
    ...people
      .filter((p) => !DIRECTORY.some((d) => d.id === p.id))
      .map((p) => ({ id: p.id, name: p.name, email: p.email })),
  ];
  const slugs = new Set(base.orgs.map((o) => o.slug));
  const orgs: SeedOrg[] = base.orgs.map((org) => ({
    org,
    weight: org.members.length,
  }));
  for (let i = orgs.length; i < SCALE.orgs; i += 1) {
    // Несколько огромных организаций и длинный хвост маленьких.
    const size =
      i === 3
        ? 6_000
        : i < 8
          ? int(r, 900, 1_800)
          : i < 60
            ? int(r, 80, 400)
            : int(r, 3, 70);
    const subject = pick(r, SUBJECTS);
    const name =
      i === 3
        ? "Студенты ФКН"
        : `${pick(r, ORG_KINDS)} «${subject}» ${String(2020 + (i % 7))}`;
    let slug = translit(`${subject.split(" ")[0] ?? "org"}-${pad(i, 3)}`).slice(
      0,
      36,
    );
    while (slugs.has(slug)) slug = `${slug}-x`;
    slugs.add(slug);
    const org: DemoOrg = {
      slug,
      name,
      project_count: Math.round(size * (0.2 + r() * 0.8)),
      members: membersOf(r, active, size, now),
      groups: [],
    };
    orgs.push({ org, weight: org.members.length });
  }
  // Группы: где больше людей, там больше групп.
  const total = orgs.reduce((sum, o) => sum + o.weight, 0);
  let made = orgs.reduce((sum, o) => sum + o.org.groups.length, 0);
  let n = 0;
  while (made < SCALE.groups) {
    let x = r() * total;
    const target = orgs.find((o) => (x -= o.weight) < 0) ?? orgs[0];
    if (!target || target.org.members.length < 3) continue;
    n += 1;
    const org = target.org;
    const size = Math.min(org.members.length, int(r, 3, 45));
    const ids = new Set<string>();
    while (ids.size < size) ids.add(pick(r, org.members).user_id);
    const prefix = weighted(r, [
      ["БПИ", 4],
      ["БЭК", 2],
      ["Команда", 3],
      ["Подгруппа", 2],
      ["Семинар", 1],
    ] as const);
    org.groups.push({
      id: `g_s${pad(n, 5)}`,
      name: `${prefix}-${String(20 + (n % 7))}${pad(n % 1000, 3)}`,
      member_ids: [...ids],
    });
    made += 1;
  }
  return { directory, orgs: orgs.map((o) => o.org) };
};

export type DemoScaleProject = {
  id: string;
  name: string;
  owner_id: string;
  owner_name: string;
  org: { id: string; slug: string; name: string } | null;
};

const TOPICS = [
  "анализ рынка",
  "рекомендательная система",
  "классификация текстов",
  "моделирование спроса",
  "оптимизация логистики",
  "мобильное приложение",
  "чат-бот для поддержки",
  "визуализация данных",
  "прогноз продаж",
  "распознавание речи",
  "сервис бронирования",
  "система контроля версий",
  "игровой движок",
  "поиск аномалий",
  "городская мобильность",
] as const;
const PROJECT_KINDS = [
  "Курсовая работа",
  "ВКР",
  "Отчёт по практике",
  "Проектная работа",
  "Эссе",
] as const;

const generateProjects = (
  r: Rand,
  people: readonly Person[],
  orgs: readonly DemoOrg[],
): DemoScaleProject[] => {
  const owners = people.filter((p) => p.project_count > 0);
  return Array.from({ length: SCALE.projects }, (_, i) => {
    const owner = pick(r, owners);
    const org = r() < 0.4 ? pick(r, orgs) : null;
    return {
      id: `p_s${pad(i + 1, 5)}`,
      name: `${pick(r, PROJECT_KINDS)}: ${pick(r, TOPICS)} ${String(i + 1)}`,
      owner_id: owner.id,
      owner_name: owner.name,
      org: org
        ? { id: `org_${org.slug}`, slug: org.slug, name: org.name }
        : null,
    };
  });
};

const CITIES = ["msk", "spb", "nn", "perm", "lab", "cloud"] as const;
const TAG_SETS: readonly (readonly string[])[] = [
  ["compile"],
  ["compile", "office"],
  ["compile", "verify", "pack"],
  ["office"],
  ["verify"],
  ["compile", "gpu"],
];

const generateRunners = (r: Rand, now: number): AdminRunner[] =>
  Array.from({ length: SCALE.runners }, (_, i) => {
    const kind = weighted(r, [
      ["online", 70],
      ["stale", 10],
      ["offline", 12],
      ["paused", 4],
      ["revoked", 4],
    ] as const);
    const seen =
      kind === "online" || kind === "paused"
        ? int(r, 1, 50)
        : kind === "stale"
          ? int(r, 70, 280)
          : kind === "revoked"
            ? int(r, 2, 40) * 86_400
            : r() < 0.15
              ? null
              : int(r, 1, 96) * 3600;
    return {
      id: `rn_s${pad(i + 1, 3)}`,
      name: `runner-${pick(r, CITIES)}-${pad(i + 1, 3)}`,
      status: "offline",
      tags: [...pick(r, TAG_SETS)],
      concurrency: pick(r, [1, 2, 2, 4, 4, 8]),
      resource_class: weighted(r, [
        ["standard", 8],
        ["large", 3],
        ["gpu", 1],
      ] as const),
      version: weighted(r, [
        ["0.3.0", 70],
        ["0.2.9", 15],
        ["0.2.4", 10],
        ["0.1.8", 5],
      ] as const),
      created_at: new Date(now - int(r, 10, 400) * DAY).toISOString(),
      last_seen_at:
        seen === null ? null : new Date(now - seen * 1000).toISOString(),
      paused: kind === "paused",
      revoked: kind === "revoked",
    };
  });

const TOKEN_LABELS = [
  "Сервер в аудитории",
  "Лаборатория",
  "Облако",
  "Резерв",
  "Тестовый стенд",
  "Кафедра",
  "GPU-узел",
] as const;

const generateTokens = (r: Rand, now: number): AdminRunnerToken[] =>
  Array.from({ length: SCALE.tokens }, (_, i) => {
    const created = now - int(r, 1, 300) * DAY;
    const uses = int(r, 0, 5);
    const max = Math.max(uses, pick(r, [1, 1, 5, 10, 50]));
    return {
      id: `rt_s${pad(i + 1, 3)}`,
      label: `${pick(r, TOKEN_LABELS)} ${String(i + 1)}`,
      created_at: new Date(created).toISOString(),
      expires_at:
        r() < 0.1
          ? null
          : new Date(created + int(r, 1, 720) * 3_600_000).toISOString(),
      max_uses: max,
      uses,
      revoked: r() < 0.12,
    };
  });

const KINDS = [
  ["compile", 70],
  ["office.convert", 15],
  ["signature.verify_detached", 8],
  ["pack.submission", 7],
] as const;
const KIND_TAG: Record<string, string> = {
  compile: "compile",
  "office.convert": "office",
  "signature.verify_detached": "verify",
  "pack.submission": "pack",
};
const ERRORS = [
  "latex_failed",
  "timeout",
  "runner_lost",
  "out_of_memory",
] as const;

const generateJobs = (
  r: Rand,
  now: number,
  people: readonly Person[],
  projects: readonly DemoScaleProject[],
  runners: readonly AdminRunner[],
): { jobs: AdminJob[]; jobOrgs: Map<string, { id: string; name: string }> } => {
  const live = runners.filter((x) => !x.revoked);
  const byId = new Map(people.map((p) => [p.id, p]));
  const jobOrgs = new Map<string, { id: string; name: string }>();
  const span = 30 * DAY;
  // Новые первыми: индекс 0 самый свежий.
  const jobs = Array.from({ length: SCALE.jobs }, (_, i): AdminJob => {
    const age = i < 60 ? i * 4_000 : 240_000 + ((i - 60) / SCALE.jobs) * span;
    const status: JobState =
      i < 35
        ? "queued"
        : i < 60
          ? "running"
          : weighted(r, [
              ["succeeded", 85],
              ["failed", 8],
              ["cancelled", 4],
              ["timed_out", 3],
            ] as const);
    const kind = weighted(r, KINDS);
    const project = pick(r, projects);
    const user = byId.get(project.owner_id);
    const runner = status === "queued" ? null : pick(r, live);
    const wait = status === "queued" ? Math.round(age / 1000) : int(r, 1, 90);
    const duration = int(r, 4, 180);
    const created = now - age;
    const started = status === "queued" ? null : created + wait * 1000;
    const finished =
      status === "queued" || status === "running" || started === null
        ? null
        : started + duration * 1000;
    const id = `job_s${pad(SCALE.jobs - i, 5)}`;
    if (project.org)
      jobOrgs.set(id, { id: project.org.id, name: project.org.name });
    return {
      id,
      kind,
      status,
      priority: kind === "compile" ? "interactive" : "checks",
      project_id: project.id,
      project_name: project.name,
      user_id: project.owner_id,
      user_name: user?.name ?? "",
      tags: [KIND_TAG[kind] ?? "compile"],
      runner_id: runner?.id ?? null,
      runner_name: runner?.name ?? null,
      attempt: status === "queued" ? 0 : r() < 0.05 ? 2 : 1,
      max_attempts: 3,
      created_at: new Date(created).toISOString(),
      started_at: started === null ? null : new Date(started).toISOString(),
      finished_at:
        finished === null
          ? null
          : new Date(Math.min(finished, now)).toISOString(),
      wait_s: wait,
      error:
        status === "failed" || status === "timed_out" ? pick(r, ERRORS) : null,
    };
  });
  return { jobs, jobOrgs };
};

const generateInvitations = (
  r: Rand,
  now: number,
  orgs: readonly DemoOrg[],
): { invitations: AdminInvitation[]; invitationOrgs: Map<string, string> } => {
  const invitationOrgs = new Map<string, string>();
  const invitations = Array.from({ length: SCALE.invitations }, (_, i) => {
    const status = weighted(r, [
      ["pending", 30],
      ["used", 50],
      ["expired", 20],
    ] as const);
    const id = `inv_s${pad(i + 1, 4)}`;
    if (r() < 0.4) invitationOrgs.set(id, pick(r, orgs).slug);
    const created = now - int(r, 0, 360) * DAY;
    const female = r() < 0.5;
    const name = translit(female ? pick(r, FEMALE) : pick(r, MALE));
    return {
      id,
      email:
        r() < 0.15
          ? null
          : `${name}.${translit(pick(r, SURNAMES))}${String(i)}@edu.hse.ru`,
      status,
      expires_at: new Date(
        status === "pending" ? now + int(r, 1, 14) * DAY : created + 7 * DAY,
      ).toISOString(),
      used_at:
        status === "used"
          ? new Date(created + int(r, 1, 6) * DAY).toISOString()
          : null,
    };
  });
  return { invitations, invitationOrgs };
};

type AuditEvent = DemoAdminPeople["audit"][number];

// Только коды, которые пишет сервер: подписи берутся из тех же ключей.
const AUDIT_ACTIONS = [
  ["auth.login", 420],
  ["auth.logout", 90],
  ["auth.login_failed", 60],
  ["project.member.set", 60],
  ["project.member.remove", 15],
  ["pat.create", 10],
  ["invite.create", 40],
  ["invite.revoke", 10],
  ["auth.register", 30],
  ["org.member.add", 60],
  ["org.member.role", 15],
  ["group.member.add", 50],
  ["group.create", 12],
  ["admin.user_approved", 20],
  ["admin.user_disabled", 8],
  ["admin.reset_link_issued", 6],
  ["runner.registration_token_create", 4],
  ["runner.pause", 3],
  ["settings.quotas_update", 2],
] as const;

/** Коды действий архива журнала: тест сверяет их с кодом сервера. */
export const DEMO_AUDIT_ACTIONS: readonly string[] = AUDIT_ACTIONS.map(
  ([action]) => action,
);

/** Журнал по id: те же действия и люди, что в живой установке. */
const auditArchive = (
  people: readonly Person[],
  orgs: readonly DemoOrg[],
  projects: readonly DemoScaleProject[],
  runners: readonly AdminRunner[],
  newest: number,
): DemoAuditArchive => {
  const count = SCALE.audit;
  const span = 365 * DAY;
  const gap = span / count;
  const admins = people.filter((p) => p.is_instance_admin);
  const at = (id: number): AuditEvent => {
    const r = rng(id * 2654435761);
    const action = weighted(r, AUDIT_ACTIONS);
    const byAdmin =
      action.startsWith("admin.") ||
      action.startsWith("runner.") ||
      action.startsWith("settings.");
    const actor = byAdmin && admins.length ? pick(r, admins) : pick(r, people);
    const other = pick(r, people);
    const org = pick(r, orgs);
    const project = pick(r, projects);
    const time = new Date(newest - (count - id) * gap - r() * gap * 0.5);
    let target: string | null = null;
    let details: Record<string, unknown> = {};
    if (action === "auth.login" || action === "auth.logout") {
      details = {
        method: r() < 0.7 ? "password" : "oidc",
        ip: `10.${String(int(r, 0, 40))}.${String(int(r, 0, 255))}.${String(int(r, 1, 254))}`,
      };
    } else if (action === "auth.login_failed") {
      details = { email: other.email, reason: "bad_password" };
      return {
        id,
        at: time.toISOString(),
        action,
        actor_id: null,
        target: null,
        details,
      };
    } else if (action.startsWith("project.")) {
      target = project.id;
      details = { title: project.name };
    } else if (action.startsWith("invite.")) {
      target = `inv_a${String(id)}`;
      details = { email: other.email };
    } else if (action.startsWith("org.")) {
      target = `org_${org.slug}`;
      details = { name: org.name, slug: org.slug, email: other.email };
    } else if (action.startsWith("group.")) {
      const group = org.groups[0];
      target = group?.id ?? `org_${org.slug}`;
      details = { name: group?.name ?? org.name, email: other.email };
    } else if (action.startsWith("admin.")) {
      target = other.id;
    } else if (action === "pat.create") {
      details = { name: "ci" };
    } else if (action.startsWith("runner.")) {
      const runner = pick(r, runners);
      target = runner.id;
      details = { name: runner.name };
    } else {
      details = { user_concurrent: 2, org_concurrent: 6 };
    }
    return {
      id,
      at: time.toISOString(),
      action,
      actor_id: actor.id,
      target,
      details,
    };
  };
  return { count, at };
};

export type DemoScaleWorld = {
  people: DemoAdminPeople;
  orgs: DemoAdminOrgs;
  ops: DemoAdminOps;
  projects: DemoScaleProject[];
};

export const createScaleWorld = (now: number = Date.now()): DemoScaleWorld => {
  const r = rng(20261030);
  const users = generatePeople(r, now);
  const orgs = generateOrgs(r, users, now);
  const projects = generateProjects(r, users, orgs.orgs);
  const runners = generateRunners(r, now);
  const { jobs, jobOrgs } = generateJobs(r, now, users, projects, runners);
  const { invitations, invitationOrgs } = generateInvitations(
    r,
    now,
    orgs.orgs,
  );
  const base = createDemoAdminOps("default", now);
  // Свежие записи журнала (как в малом мире) идут после архива.
  const newestArchive = now - 2 * DAY - 3_600_000;
  const recent = RECENT_AUDIT.map(({ minutesAgo, ...e }, n) => ({
    ...e,
    id: SCALE.audit + RECENT_AUDIT.length - n,
    at: new Date(now - minutesAgo * 60_000).toISOString(),
  }));
  const owners = [
    ...users
      .filter((u) => u.project_count > 0)
      .map((u) => ({ id: u.id, name: u.name, projects: u.project_count })),
  ]
    .sort((a, b) => b.projects - a.projects || (a.id < b.id ? -1 : 1))
    .slice(0, 10);
  return {
    people: {
      users,
      invitations,
      audit: recent,
      archive: auditArchive(users, orgs.orgs, projects, runners, newestArchive),
      invitationOrgs,
    },
    orgs,
    ops: {
      ...base,
      runners,
      tokens: generateTokens(r, now),
      jobs,
      jobOrgs,
      services: base.services.map((s) =>
        s.kind === "runners"
          ? {
              ...s,
              online: runners.filter((x) => !x.revoked && !x.paused).length,
              total: runners.filter((x) => !x.revoked).length,
            }
          : s,
      ),
      storage: {
        ...base.storage,
        blob_count: 412_000,
        blob_bytes: Math.round(1.4 * 1024 ** 4),
        projects: SCALE.projects,
        deleted_projects: 214,
        free_bytes: Math.round(2.1 * 1024 ** 4),
        volume_total_bytes: 4 * 1024 ** 4,
        owners,
      },
    },
    projects,
  };
};
