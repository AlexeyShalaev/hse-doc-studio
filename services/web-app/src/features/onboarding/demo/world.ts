import type { DemoEvent } from "../model/scenario";
import type { DemoComment, DemoContent, DemoPrompt } from "./content";

/**
 * Песочница демо-проекта: весь проект в памяти вкладки, без единого запроса к
 * серверу. Сборка, ответ ИИ и git только изображают работу (с задержками), поэтому
 * тур проходит и на сервере без раннеров и без ИИ-провайдера.
 */

export type DemoFile = { path: string; content: string };
export type DemoCommit = { sha: string; message: string; pushed: boolean };
export type ChatMessage = {
  id: string;
  role: "user" | "agent";
  text: string;
  streaming?: boolean;
};

export type PreviewPage =
  | { kind: "title"; title: string; author: string; footer: string }
  | {
      kind: "body";
      abstract: string | null;
      sections: { heading: string; text: string }[];
    };

export type DemoState = {
  project: { name: string; template: string } | null;
  files: DemoFile[];
  activePath: string;
  /** Есть правки после последней сборки. */
  dirty: boolean;
  build: {
    status: "idle" | "running" | "done";
    log: string[];
    pages: PreviewPage[];
  };
  chat: ChatMessage[];
  agentBusy: boolean;
  comments: (DemoComment & { resolved: boolean })[];
  git: {
    remote: string | null;
    commits: DemoCommit[];
    busy: boolean;
    /** Правки, ещё не попавшие ни в один коммит. */
    uncommitted: boolean;
  };
};

export type Sleep = (ms: number) => Promise<void>;

export type DemoWorldOptions = {
  content: DemoContent;
  /** Ускорение для тестов и автопоказа; 1 — обычный темп. */
  speed?: number;
  sleep?: Sleep;
};

const MAIN = "main.tex";

const realSleep: Sleep = (ms) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

const strip = (text: string): string =>
  text
    .replace(/\\[a-zA-Z]+\*?(\{[^}]*\})?/g, (_m, arg: string | undefined) =>
      arg ? arg.slice(1, -1) : "",
    )
    .replace(/\s+/g, " ")
    .trim();

const between = (source: string, re: RegExp): string | null => {
  const match = re.exec(source);
  return match?.[1] ? match[1].trim() : null;
};

/** Превью «PDF» из исходника: титульный лист и страница с аннотацией и разделами. */
export const renderPreview = (
  source: string,
  footer: string,
): PreviewPage[] => {
  const title = between(source, /\\title\{([^}]*)\}/) ?? "";
  const author = between(source, /\\author\{([^}]*)\}/) ?? "";
  const abstractRaw = between(
    source,
    /\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/,
  );
  const body = source.split(/\\section\{/).slice(1);
  const sections = body.map((chunk) => {
    const close = chunk.indexOf("}");
    const heading = chunk.slice(0, close);
    const text = strip(
      chunk.slice(close + 1).replace(/\\end\{document\}[\s\S]*$/, ""),
    );
    return { heading: heading.trim(), text };
  });
  return [
    { kind: "title", title, author, footer },
    {
      kind: "body",
      abstract: abstractRaw ? strip(abstractRaw) : null,
      sections,
    },
  ];
};

let counter = 0;
const nextId = (prefix: string): string => {
  counter += 1;
  return `${prefix}-${String(counter)}`;
};

const fakeSha = (seed: number): string =>
  ((seed * 2654435761) >>> 0).toString(16).padStart(8, "0").slice(0, 7);

export type DemoWorld = ReturnType<typeof createDemoWorld>;

export const createDemoWorld = (options: DemoWorldOptions) => {
  const { content } = options;
  const speed = options.speed ?? 1;
  const sleep = options.sleep ?? realSleep;
  const wait = (ms: number) => sleep(Math.round(ms / speed));

  let state: DemoState = {
    project: null,
    files: [],
    activePath: MAIN,
    dirty: false,
    build: { status: "idle", log: [], pages: [] },
    chat: [],
    agentBusy: false,
    comments: [{ ...content.supervisorComment, resolved: false }],
    git: { remote: null, commits: [], busy: false, uncommitted: false },
  };
  const listeners = new Set<() => void>();
  const eventListeners = new Set<(event: DemoEvent) => void>();

  const set = (patch: (s: DemoState) => DemoState) => {
    state = patch(state);
    listeners.forEach((l) => {
      l();
    });
  };
  const emit = (event: DemoEvent) => {
    eventListeners.forEach((l) => {
      l(event);
    });
  };
  const mainSource = () =>
    state.files.find((f) => f.path === MAIN)?.content ?? "";

  const setFile = (path: string, value: string) => {
    set((s) => ({
      ...s,
      files: s.files.map((f) =>
        f.path === path ? { ...f, content: value } : f,
      ),
      dirty: true,
      git: { ...s.git, uncommitted: true },
    }));
  };

  return {
    getState: (): DemoState => state,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    onEvent: (listener: (event: DemoEvent) => void) => {
      eventListeners.add(listener);
      return () => {
        eventListeners.delete(listener);
      };
    },

    createProject: (template?: string) => {
      if (state.project) return;
      const templateName = template ?? content.templateFallback;
      set((s) => ({
        ...s,
        project: { name: content.projectName, template: templateName },
        files: [
          {
            path: MAIN,
            content: content.source(content.placeholderTopic, content.author),
          },
          {
            path: "references.bib",
            content:
              "@book{sommerville2016,\n  author = {Sommerville, Ian},\n  title = {Software Engineering},\n  year = {2016}\n}\n",
          },
          { path: "images/", content: "" },
        ],
        activePath: MAIN,
      }));
      emit("project-created");
    },

    openFile: (path: string) => {
      set((s) => ({ ...s, activePath: path }));
    },

    editFile: (path: string, value: string) => {
      setFile(path, value);
      if (path === MAIN && !value.includes(content.placeholderTopic)) {
        emit("edited");
      }
    },

    /** «Вписать за меня»: тема вместо заглушки в \title. */
    insertTopic: () => {
      const source = mainSource();
      if (!source.includes(content.placeholderTopic)) {
        emit("edited");
        return;
      }
      setFile(MAIN, source.replace(content.placeholderTopic, content.topic));
      set((s) => ({ ...s, activePath: MAIN }));
      emit("edited");
    },

    build: async () => {
      if (state.build.status === "running" || !state.project) return;
      set((s) => ({ ...s, build: { ...s.build, status: "running", log: [] } }));
      for (const line of content.buildLog) {
        await wait(350);
        set((s) => ({
          ...s,
          build: { ...s.build, log: [...s.build.log, line] },
        }));
      }
      set((s) => ({
        ...s,
        dirty: false,
        build: {
          status: "done",
          log: s.build.log,
          pages: renderPreview(mainSource(), content.previewFooter),
        },
      }));
      emit("built");
    },

    askAgent: async (promptId: DemoPrompt["id"]) => {
      if (state.agentBusy) return;
      const prompt = content.prompts.find((p) => p.id === promptId);
      if (!prompt) return;
      const replyId = nextId("agent");
      set((s) => ({
        ...s,
        agentBusy: true,
        chat: [
          ...s.chat,
          { id: nextId("user"), role: "user", text: prompt.label },
          { id: replyId, role: "agent", text: "", streaming: true },
        ],
      }));
      await wait(500);
      const words = content.replies[promptId].split(" ");
      for (let i = 0; i < words.length; i += 3) {
        await wait(60);
        const chunk = words.slice(0, i + 3).join(" ");
        set((s) => ({
          ...s,
          chat: s.chat.map((m) =>
            m.id === replyId ? { ...m, text: chunk } : m,
          ),
        }));
      }
      const fresh = content.agentComments.filter(
        (c) => !state.comments.some((x) => x.id === c.id),
      );
      set((s) => ({
        ...s,
        agentBusy: false,
        chat: s.chat.map((m) =>
          m.id === replyId ? { ...m, streaming: false } : m,
        ),
        comments: [
          ...s.comments,
          ...fresh.map((c) => ({ ...c, resolved: false })),
        ],
      }));
      emit("agent-done");
    },

    /** Принять замечание: правка в текст (для ИИ) и отметка «решено». */
    resolveComment: (id?: string) => {
      const target =
        state.comments.find((c) => c.id === id && !c.resolved) ??
        state.comments.find((c) => c.kind === "agent" && !c.resolved) ??
        state.comments.find((c) => !c.resolved);
      if (!target) {
        emit("review-resolved");
        return;
      }
      if (target.id === "c-style") {
        const source = mainSource();
        const fixed = source
          .replace("до сих пор часто ведётся", "нередко ведётся")
          .replace("still often tracked", "frequently tracked");
        if (fixed !== source) setFile(MAIN, fixed);
      }
      set((s) => ({
        ...s,
        comments: s.comments.map((c) =>
          c.id === target.id ? { ...c, resolved: true } : c,
        ),
      }));
      emit("review-resolved");
    },

    connectRemote: async (url?: string) => {
      if (state.git.remote || state.git.busy) return;
      set((s) => ({ ...s, git: { ...s.git, busy: true } }));
      await wait(600);
      set((s) => ({
        ...s,
        git: {
          ...s.git,
          busy: false,
          remote: url?.trim() ? url.trim() : content.remoteUrl,
        },
      }));
    },

    /** Синхронизация: коммит несохранённых правок и отправка всех коммитов. */
    sync: async () => {
      if (state.git.busy) return;
      if (!state.git.remote) {
        set((s) => ({ ...s, git: { ...s.git, busy: true } }));
        await wait(600);
        set((s) => ({ ...s, git: { ...s.git, remote: content.remoteUrl } }));
      }
      set((s) => ({ ...s, git: { ...s.git, busy: true } }));
      await wait(400);
      if (state.git.uncommitted || state.git.commits.length === 0) {
        const message = state.comments.some((c) => c.resolved)
          ? content.commitMessages.review
          : content.commitMessages.edit;
        set((s) => ({
          ...s,
          git: {
            ...s.git,
            uncommitted: false,
            commits: [
              {
                sha: fakeSha(s.git.commits.length + 7),
                message,
                pushed: false,
              },
              ...s.git.commits,
            ],
          },
        }));
      }
      await wait(700);
      set((s) => ({
        ...s,
        git: {
          ...s.git,
          busy: false,
          commits: s.git.commits.map((c) => ({ ...c, pushed: true })),
        },
      }));
      emit("git-pushed");
    },
  };
};
