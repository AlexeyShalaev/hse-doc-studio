import { describe, expect, it } from "vitest";
import {
  ChatContentBlockSchema,
  ChatMessageSchema,
  ChatSessionSchema,
  PersonaListSchema,
} from "./agentChat.schema";

describe("agentChat schemas", () => {
  it("parses a chat session", () => {
    const parsed = ChatSessionSchema.parse({
      id: "s1",
      title: "Новый чат",
      doc_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      archived: false,
      message_count: 0,
      last_run_id: null,
      default_provider_id: null,
      default_model: null,
    });
    expect(parsed.title).toBe("Новый чат");
    // persona fields default to null when absent (old backend / fresh chat).
    expect(parsed.persona).toBeNull();
    expect(parsed.persona_instructions).toBeNull();
  });

  it("parses a chat session carrying a persona", () => {
    const parsed = ChatSessionSchema.parse({
      id: "s2",
      title: "Чат",
      doc_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      archived: false,
      message_count: 0,
      last_run_id: null,
      default_provider_id: null,
      default_model: null,
      persona: "custom",
      persona_instructions: "Будь нормоконтролёром",
    });
    expect(parsed.persona).toBe("custom");
    expect(parsed.persona_instructions).toBe("Будь нормоконтролёром");
  });

  it("parses the persona list", () => {
    const personas = PersonaListSchema.parse([
      { id: "default", label: "Базовый", description: "Нейтральный" },
      { id: "methodologist", label: "Методист", description: "Структура" },
    ]);
    expect(personas).toHaveLength(2);
    expect(personas[1]?.id).toBe("methodologist");
  });

  it("defaults content-block args and is_error", () => {
    const block = ChatContentBlockSchema.parse({
      kind: "text",
      text: "привет",
    });
    expect(block.args).toEqual({});
    expect(block.is_error).toBe(false);
  });

  it("parses an assistant message carrying a tool_call block", () => {
    const message = ChatMessageSchema.parse({
      id: "m1",
      seq: 0,
      role: "assistant",
      created_at: "2026-01-01T00:00:00Z",
      approval: "auto",
      blocks: [
        {
          kind: "tool_call",
          call_id: "c1",
          tool_name: "read_tex",
          args: { path: "a.tex" },
        },
      ],
    });
    expect(message.blocks[0]?.tool_name).toBe("read_tex");
    expect(message.blocks[0]?.args).toEqual({ path: "a.tex" });
  });
});
