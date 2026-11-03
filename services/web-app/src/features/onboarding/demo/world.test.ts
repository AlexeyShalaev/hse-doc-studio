import { describe, expect, it } from "vitest";
import { DEMO_CONTENT, demoContentFor } from "./content";
import { createDemoWorld, renderPreview } from "./world";
import type { DemoEvent } from "../model/scenario";

const instant = () => Promise.resolve();

const makeWorld = (lang = "ru") => {
  const world = createDemoWorld({
    content: demoContentFor(lang),
    sleep: instant,
  });
  const events: DemoEvent[] = [];
  world.onEvent((e) => events.push(e));
  return { world, events };
};

const shape = (value: unknown): unknown =>
  Array.isArray(value)
    ? value.map(shape)
    : value && typeof value === "object"
      ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shape(v)]))
      : typeof value;

describe("содержимое демо", () => {
  it("ru и en совпадают по форме", () => {
    expect(shape(DEMO_CONTENT.en)).toEqual(shape(DEMO_CONTENT.ru));
  });
});

describe("песочница демо-проекта", () => {
  it("полный сценарий: шаблон, правка, сборка, ИИ, замечание, git", async () => {
    const { world, events } = makeWorld();
    const content = demoContentFor("ru");

    world.createProject("Курсовая");
    expect(world.getState().project?.template).toBe("Курсовая");
    world.insertTopic();
    await world.build();
    const title = world.getState().build.pages[0];
    expect(title?.kind === "title" && title.title).toBe(content.topic);

    await world.askAgent("check");
    const chat = world.getState().chat;
    expect(chat.at(-1)?.text).toBe(content.replies.check);
    expect(chat.at(-1)?.streaming).toBe(false);
    expect(
      world.getState().comments.filter((c) => c.kind === "agent"),
    ).toHaveLength(2);

    world.resolveComment();
    const source = world.getState().files[0]?.content ?? "";
    expect(source).toContain("нередко ведётся");
    expect(world.getState().dirty).toBe(true);

    await world.sync();
    const git = world.getState().git;
    expect(git.remote).toBe(content.remoteUrl);
    expect(git.commits).toHaveLength(1);
    expect(git.commits[0]?.pushed).toBe(true);
    expect(git.commits[0]?.message).toBe(content.commitMessages.review);

    expect(events).toEqual([
      "project-created",
      "edited",
      "built",
      "agent-done",
      "review-resolved",
      "git-pushed",
    ]);
  });

  it("ручная правка без заглушки темы считается выполненной", () => {
    const { world, events } = makeWorld("en");
    world.createProject();
    const source = world.getState().files[0]?.content ?? "";
    world.editFile("main.tex", source.replace("Your thesis topic", "My topic"));
    expect(events).toContain("edited");
  });

  it("сборка без проекта ничего не делает", async () => {
    const { world, events } = makeWorld();
    await world.build();
    expect(world.getState().build.status).toBe("idle");
    expect(events).toEqual([]);
  });

  it("ответ агента идёт потоком: подписчик видит частичный текст", async () => {
    const { world } = makeWorld();
    world.createProject();
    const seen: string[] = [];
    world.subscribe(() => {
      const last = world.getState().chat.at(-1);
      if (last?.role === "agent" && last.streaming) seen.push(last.text);
    });
    await world.askAgent("shorten");
    expect(seen.length).toBeGreaterThan(2);
    expect(seen.some((s) => s.length > 0 && s.length < 40)).toBe(true);
  });
});

describe("превью из исходника", () => {
  it("титул, аннотация и разделы", () => {
    const pages = renderPreview(
      demoContentFor("ru").source("Тема", "Автор"),
      "Москва",
    );
    expect(pages[0]).toEqual({
      kind: "title",
      title: "Тема",
      author: "Автор",
      footer: "Москва",
    });
    const body = pages[1];
    expect(body?.kind).toBe("body");
    if (body?.kind !== "body") return;
    expect(body.abstract).toContain("автоматизации");
    expect(body.sections.map((s) => s.heading)).toEqual([
      "Введение",
      "Анализ требований",
    ]);
  });
});
