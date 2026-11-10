import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import type { z } from "zod";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { SignaturePlanSchema } from "@entities/signature";
import { signingRouteApi } from "@entities/signing-route";
import {
  SR_AUTHOR,
  makeRouteParticipant,
  makeSigningRoute,
} from "@entities/signing-route/testing";
import { useRouteSlotHints } from "./useRouteSlotHints";

// План подписей точки, которую держит маршрут: случай с сервера. Автор (открепленная ЭП) согласовал
// при отправке, научрук (картинка) ещё не принял приглашение; старая ручная фиксация устарела.

type Plan = z.infer<typeof SignaturePlanSchema>;

const DOC = "topic_application";

const plan = (held: boolean): Plan =>
  SignaturePlanSchema.parse({
    profile_id: "topic-approval",
    total: 2,
    signed: 0,
    crypto_total: 1,
    crypto_signed: 0,
    waiting_for_me: 0,
    route: {
      id: "sr_1",
      profile_id: "topic-approval",
      status: "active",
      phase: "approval",
      round: 1,
      current_step: 2,
      steps_total: 2,
    },
    docs: [
      {
        doc_id: DOC,
        built: true,
        held_by_route: held,
        slots: [
          {
            slot_id: "author",
            label: { ru: "Автор работы" },
            signer: { persona: "author", name: SR_AUTHOR.name },
            mode: "detached_text",
            method: "detached",
            crypto: true,
            mark: "plate",
            status: "stale",
            reason: "rebuilt",
            hint: "Документ пересобран после фиксации: зафиксируйте PDF заново и подпишите новую версию",
            is_mine: true,
            route_state: "waiting",
          },
        ],
      },
    ],
  });

const ROUTE = makeSigningRoute({
  id: "sr_1",
  phase: "approval",
  current_step: 2,
  docs: [
    {
      doc_id: DOC,
      name: { ru: "Заявление" },
      frozen: false,
      slots: [
        {
          slot_id: "author",
          label: { ru: "Автор работы" },
          participant_id: "srp_author",
          optional: false,
          status: "stale",
        },
        {
          slot_id: "supervisor",
          label: { ru: "Научный руководитель" },
          participant_id: "srp_sup",
          optional: false,
          status: "pending",
        },
      ],
    },
  ],
  steps: [
    [
      makeRouteParticipant({
        method: "detached",
        state: "waiting",
        next_action: "wait",
      }),
    ],
    [
      makeRouteParticipant({
        id: "srp_sup",
        persona: "supervisor",
        user_id: null,
        invitation_id: "inv_1",
        name: "h***@hse.ru",
        card_name: "Салех Х. М.",
        membership: "invited",
        assignments: [{ doc_id: DOC, slot_id: "supervisor" }],
        method: "image",
        state: "invited",
        next_action: "wait",
        changes_visible: true,
        approved_at: null,
      }),
    ],
  ],
});

const wrapper = ({ children }: { children: ReactNode }) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {children}
    </QueryClientProvider>
  </I18nextProvider>
);

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  vi.spyOn(sessionApi, "bootstrap").mockResolvedValue({
    ...LOCAL_BOOTSTRAP,
    mode: "server",
    user: {
      id: SR_AUTHOR.id,
      name: SR_AUTHOR.name,
      email: "author@edu.hse.ru",
      avatar_initials: "ИИ",
      is_instance_admin: false,
      email_verified: true,
      locale: null,
      org_roles: [],
    },
  });
  vi.spyOn(signingRouteApi, "get").mockResolvedValue(ROUTE);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useRouteSlotHints", () => {
  it("свой слот на маршруте: почему и когда, вместо «зафиксируйте заново»", async () => {
    const { result } = renderHook(() => useRouteSlotHints("p1", plan(true)), {
      wrapper,
    });
    expect(result.current.heldMine).toBe(true);
    // Пока ход маршрута грузится, сказано только, что PDF зафиксирует маршрут.
    expect(result.current.hint(DOC, "author")).toBe(
      "PDF зафиксирует маршрут, когда все согласуют.",
    );
    await waitFor(() => {
      expect(result.current.hint(DOC, "author")).toBe(
        "Вы уже согласовали. Электронную подпись Студия попросит поставить после фиксации PDF, когда согласуют: Научный руководитель Салех Х. М. (шаг 2 из 2, приглашение не принято).",
      );
    });
    expect(result.current.hint(DOC, "supervisor")).toBe(
      "Научный руководитель Салех Х. М.: приглашение в проект ещё не принято.",
    );
  });

  it("документ свободен: подсказка плана в силе", () => {
    const { result } = renderHook(() => useRouteSlotHints("p1", plan(false)), {
      wrapper,
    });
    expect(result.current.heldMine).toBe(false);
    expect(result.current.hint(DOC, "author")).toBeNull();
  });
});
