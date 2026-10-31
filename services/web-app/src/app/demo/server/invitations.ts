import type {
  AccessRequestView,
  MyAccessRequest,
  MyInvitation,
  MyTransfer,
  Notification,
  ProjectInvitation,
  ProjectInvitationPreview,
} from "@entities/invitation";
import type { ServerDemoWorld } from "./world";

// Демо-мир трека invites: приглашения, запросы доступа, передачи владения и «Входящие».
// Состояние живёт рядом с миром (WeakMap), а не в нём: сброс сценария создаёт новый мир и новое состояние.

export type DemoTransfer = {
  projectId: string;
  to: { kind: "user" | "org"; id: string; name: string };
  created_at: string;
  expires_at: string;
  message: string | null;
};

export type DemoInvites = {
  /** Приглашения по проектам (глазами пригласившего). */
  projectInvitations: Record<string, ProjectInvitation[]>;
  /** Запросы доступа по проектам. */
  projectRequests: Record<string, AccessRequestView[]>;
  /** Ожидающая передача по проекту. */
  transfers: Record<string, DemoTransfer | undefined>;
  myInvitations: MyInvitation[];
  myTransfers: MyTransfer[];
  myRequests: MyAccessRequest[];
  notifications: Notification[];
  previews: Record<string, ProjectInvitationPreview>;
  seq: number;
};

export const DEMO_INVITE_PROJECT_ID = "p_01hxa1c4de";
const DAY = 86_400_000;
const iso = (offsetDays: number): string =>
  new Date(Date.UTC(2026, 10, 1, 9) + offsetDays * DAY).toISOString();

const ANNA = { id: "u_01hx7k2m9c", name: "Анна Петрова" };
const PAVEL = { id: "u_01hx7k5pavel", name: "Павел Орлов" };

const seed = (): DemoInvites => ({
  projectInvitations: {
    [DEMO_INVITE_PROJECT_ID]: [
      {
        id: "inv_demo_user",
        invitee: {
          kind: "user",
          user_id: "u_01hx7k5q7h",
          name: "Ольга Белова",
          email_hint: null,
        },
        role: "reviewer",
        persona: "supervisor",
        can_share: false,
        show_sources: true,
        can_edit_all: false,
        message: "Посмотрите, пожалуйста, главу 2",
        invited_by: ANNA,
        created_at: iso(-1),
        expires_at: iso(5),
        status: "pending",
        sent_count: 2,
        last_sent_at: iso(-1),
      },
      {
        id: "inv_demo_email",
        invitee: {
          kind: "email",
          user_id: null,
          name: null,
          email_hint: "petr@hse.ru",
        },
        role: "editor",
        persona: null,
        can_share: false,
        show_sources: true,
        can_edit_all: false,
        message: null,
        invited_by: ANNA,
        created_at: iso(-9),
        expires_at: iso(-2),
        status: "expired",
        sent_count: 1,
        last_sent_at: iso(-9),
      },
    ],
  },
  projectRequests: {
    [DEMO_INVITE_PROJECT_ID]: [
      {
        id: "arq_demo_vera",
        requester: {
          id: "u_demo_vera",
          name: "Вера Смирнова",
          email: "vera@hse.ru",
        },
        message: "Я соавтор главы 3",
        status: "pending",
        created_at: iso(0),
        decided_at: null,
        decided_by: null,
        granted_role: null,
      },
    ],
  },
  transfers: {},
  myInvitations: [
    {
      id: "inv_demo_mine",
      project: {
        id: "p_01hxa3k2jm",
        name: "Анализ нагрузки на очередь задач",
        owner_name: PAVEL.name,
      },
      role: "editor",
      persona: null,
      message: "Подключайся к разделу про очереди",
      invited_by: PAVEL,
      created_at: iso(0),
      expires_at: iso(7),
      status: "pending",
    },
    {
      id: "inv_demo_old",
      project: {
        id: "p_demo_old",
        name: "Практика 2024",
        owner_name: "Иван Сидоров",
      },
      role: "reader",
      persona: null,
      message: null,
      invited_by: { id: "u_01hx7k1a0b", name: "Иван Сидоров" },
      created_at: iso(-20),
      expires_at: iso(-13),
      status: "expired",
    },
  ],
  myTransfers: [
    {
      id: "trf_demo_mine",
      project: { id: "p_01hxa3k2jm", name: "Анализ нагрузки на очередь задач" },
      from: { kind: "user", name: PAVEL.name },
      message: null,
      created_at: iso(0),
      expires_at: iso(7),
      status: "pending",
      previous_owner_role: "editor",
    },
  ],
  myRequests: [
    {
      id: "arq_demo_mine",
      project: { id: "p_01hxa9foreign", name: null },
      status: "pending",
      created_at: iso(-1),
      decided_at: null,
      granted_role: null,
    },
  ],
  notifications: [
    {
      id: "ntf_demo_request",
      kind: "access_request",
      created_at: iso(0),
      read_at: null,
      payload: {
        project_id: DEMO_INVITE_PROJECT_ID,
        project_name: "Bertie: курсовой проект",
        actor_name: "Вера Смирнова",
        role: null,
        ref_id: "arq_demo_vera",
        outcome: null,
      },
    },
    {
      id: "ntf_demo_accepted",
      kind: "invitation_accepted",
      created_at: iso(-1),
      read_at: null,
      payload: {
        project_id: DEMO_INVITE_PROJECT_ID,
        project_name: "Bertie: курсовой проект",
        actor_name: "Дмитрий Кузнецов",
        role: "editor",
        ref_id: "inv_demo_done",
        outcome: "accepted",
      },
    },
    {
      id: "ntf_demo_decided",
      kind: "access_request_decided",
      created_at: iso(-3),
      read_at: iso(-2),
      payload: {
        project_id: "p_01hxa2f8gh",
        project_name: "Industry adoption of CI",
        actor_name: "Иван Сидоров",
        role: "reviewer",
        ref_id: "arq_demo_old",
        outcome: "approved",
      },
    },
    {
      id: "ntf_demo_removed",
      kind: "member_removed",
      created_at: iso(-6),
      read_at: iso(-5),
      payload: {
        project_id: "p_demo_gone",
        project_name: "Хакатон 2025",
        actor_name: "Елена Миронова",
        role: null,
        ref_id: null,
        outcome: null,
      },
    },
  ],
  previews: {
    hspi_demo_ok: {
      state: "ok",
      project_name: "ВКР: Анализ требований",
      inviter_name: ANNA.name,
      role: "reviewer",
      email_hint: "a***@example.org",
      registration_token: null,
    },
    hspi_demo_signup: {
      state: "ok",
      project_name: "ВКР: Анализ требований",
      inviter_name: ANNA.name,
      role: "reviewer",
      email_hint: "p***@hse.ru",
      registration_token: "hspi_demo_signup",
    },
    hspi_demo_mismatch: {
      state: "ok",
      project_name: "ВКР: Анализ требований",
      inviter_name: ANNA.name,
      role: "editor",
      email_hint: "p***@hse.ru",
      registration_token: null,
    },
    hspi_demo_expired: {
      state: "expired",
      project_name: null,
      inviter_name: null,
      role: null,
      email_hint: null,
      registration_token: null,
    },
    hspi_demo_used: {
      state: "used",
      project_name: null,
      inviter_name: null,
      role: null,
      email_hint: null,
      registration_token: null,
    },
  },
  seq: 0,
});

const states = new WeakMap<ServerDemoWorld, DemoInvites>();

export const invitesOf = (world: ServerDemoWorld): DemoInvites => {
  let state = states.get(world);
  if (!state) {
    state = seed();
    states.set(world, state);
  }
  return state;
};

export const nextId = (state: DemoInvites, prefix: string): string => {
  state.seq += 1;
  return `${prefix}_demo_${String(state.seq)}`;
};
