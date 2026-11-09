import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { I18nextProvider } from "react-i18next";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { i18n } from "@shared/lib";
import { loadSigningNamespace } from "@shared/lib/i18n/signingNamespace";
import { createSignerProfileDemo } from "@entities/signer-profile/testing";
import { createSigningIdentityDemo } from "@entities/signing-identity/testing";
import { signingRouteApi, signingTaskApi } from "@entities/signing-route";
import {
  createSigningRouteDemo,
  type SigningDemoMember,
  type SigningDemoUser,
} from "@entities/signing-route/testing";

// Подпись прямо на странице подписанта (срез W5) на моках контракта: картинка, ключ Студии
// с паролем, создание ключа, запрет ключей на сервере, готовая подпись, КриптоПро.

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));
// Холста в jsdom нет: растр нарисованной подписи подменяем готовым PNG.
vi.mock("@features/signing-inline/lib/strokes", async () => ({
  ...(await vi.importActual<Record<string, unknown>>(
    "@features/signing-inline/lib/strokes",
  )),
  strokesToPng: () =>
    Promise.resolve(new Blob(["drawn"], { type: "image/png" })),
}));
// Плагина КриптоПро в тестах нет: один сертификат и подпись из трёх байт.
const cades = vi.hoisted(() => ({
  signDetached: vi.fn(() => Promise.resolve(new Uint8Array([1, 2, 3]))),
  exportCertificatePem: vi.fn(() =>
    Promise.resolve("-----BEGIN CERTIFICATE-----"),
  ),
}));
vi.mock("@features/signature-stamper", async () => ({
  ...(await vi.importActual<Record<string, unknown>>(
    "@features/signature-stamper",
  )),
  loadCadesPlugin: () => Promise.resolve({}),
  listCertificates: () =>
    Promise.resolve([
      {
        thumbprint: "AB12",
        subject: "Петров Пётр Петрович",
        issuer: "УЦ ФНС России",
        validFrom: new Date("2026-01-01T00:00:00Z"),
        validTo: new Date("2027-01-01T00:00:00Z"),
        hasPrivateKey: true,
      },
    ]),
  exportCertificatePem: cades.exportCertificatePem,
  signDetached: cades.signDetached,
}));

import { SigningPage } from "./SigningPage";

const PROJECT = "p_01hxa1c4de";
const PROFILE = "topic-approval";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const SUPERVISOR: SigningDemoUser = {
  id: "u_demo_petrov",
  name: "Петров П. П.",
};
const ACADEMIC: SigningDemoUser = { id: "u_sidorov", name: "Сидоров С. С." };

const PLATE = {
  owner: SUPERVISOR.name,
  kind: "openpgp",
  cert_id: "1A2B 3C4D 5E6F 7A8B",
} as const;
const supervisorMember: SigningDemoMember = {
  user_id: SUPERVISOR.id,
  name: SUPERVISOR.name,
  persona: "supervisor",
  plate: PLATE,
};

let me: SigningDemoUser = AUTHOR;
let keysAllowed = true;
const identities = createSigningIdentityDemo({
  getUser: () => me,
  allowed: () => keysAllowed,
});
const profiles = createSignerProfileDemo({ getUser: () => me });
const demo = createSigningRouteDemo({
  getUser: () => me,
  members: [
    supervisorMember,
    {
      user_id: ACADEMIC.id,
      name: ACADEMIC.name,
      persona: "academic_supervisor",
    },
  ],
  serverKeysAllowed: () => keysAllowed,
  keysOf: (user) =>
    identities.keysOf(user.id).map((key) => ({
      id: key.id,
      label: key.label,
      kind: key.kind,
      protected: key.protected,
      signer: key.subject_cn,
    })),
  onRememberImage: (user, image) => {
    profiles.saveImage(user.id, image);
  },
});

/** Автор отправил «Заявку на тему КП»: он, научрук ЭП и, если нужно, академрук картинкой. */
const sendRoute = async (withAcademic: boolean): Promise<string> => {
  me = AUTHOR;
  const route = await signingRouteApi.create(PROJECT, PROFILE);
  const steps = route.steps.map((step) =>
    step.map((p) => ({
      id: p.id,
      persona: p.persona,
      user_id: p.user_id,
      invitation_id: p.invitation_id,
    })),
  );
  await signingRouteApi.update(PROJECT, route.id, {
    steps: withAcademic
      ? [
          ...steps,
          [
            {
              id: null,
              persona: "academic_supervisor",
              user_id: ACADEMIC.id,
              invitation_id: null,
            },
          ],
        ]
      : steps,
    extra_slots: withAcademic
      ? [{ doc_id: "topic_application", slot_id: "academic_supervisor" }]
      : [],
    deadline: null,
    message: null,
  });
  const preview = await signingRouteApi.preview(PROJECT, route.id);
  await signingRouteApi.send(PROJECT, route.id, {
    expected: Object.fromEntries(
      preview.docs.map((d) => [d.doc_id, d.token ?? ""]),
    ),
    sign: null,
  });
  return route.id;
};

const approveAs = async (routeId: string, as: SigningDemoUser) => {
  me = as;
  const task = await signingTaskApi.get(PROJECT, routeId);
  await signingTaskApi.approve(PROJECT, routeId, {
    expected: { topic_application: task.docs[0]?.token ?? "" },
    method: null,
    sign: null,
  });
};

/** Научрук согласовал до фиксации, академрук поставил картинку: научрук подписывает итоговый PDF. */
const routeAtFinalSign = async (): Promise<string> => {
  const routeId = await sendRoute(true);
  await approveAs(routeId, SUPERVISOR);
  me = ACADEMIC;
  await signingTaskApi.uploadImage(
    PROJECT,
    routeId,
    new Blob(["png"], { type: "image/png" }),
    false,
  );
  await approveAs(routeId, ACADEMIC);
  return routeId;
};

const open = (routeId: string, as: SigningDemoUser) => {
  me = as;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/sign/${PROJECT}/${routeId}`]}>
          <Routes>
            <Route path="/sign/:projectId/:routeId" element={<SigningPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
};

const pageState = () =>
  screen.getByTestId("signing-page").getAttribute("data-state");
const primary = () => screen.getByTestId("signing-primary");

beforeAll(async () => {
  // jsdom без холста: рисование не должно сыпать «not implemented».
  HTMLCanvasElement.prototype.getContext = (() =>
    null) as typeof HTMLCanvasElement.prototype.getContext;
  installDemoAdapter(
    apiClient,
    createDemoRouter([
      ...demo.routes,
      ...identities.routes,
      ...profiles.routes,
    ]),
  );
  await loadSigningNamespace();
});

beforeEach(async () => {
  demo.reset();
  identities.reset();
  profiles.reset();
  cades.signDetached.mockClear();
  cades.exportCertificatePem.mockClear();
  keysAllowed = true;
  supervisorMember.plate = PLATE;
  me = AUTHOR;
  await i18n.changeLanguage("ru");
});

describe("подпись картинкой на странице", () => {
  it("рисует подпись, запоминает её в профиле и согласует", async () => {
    const user = userEvent.setup();
    const routeId = await sendRoute(true);
    await approveAs(routeId, SUPERVISOR);
    open(routeId, ACADEMIC);
    await waitFor(() => {
      expect(pageState()).toBe("turn");
    });
    expect(
      screen.queryByTestId("signing-method-placeholder"),
    ).not.toBeInTheDocument();

    // Без картинки кнопка показывает, чего не хватает.
    expect(primary()).toHaveAttribute("data-blocked", "image");
    await user.click(primary());
    expect(screen.getByTestId("signing-image")).toHaveTextContent(
      "Нужна картинка подписи.",
    );
    expect(pageState()).toBe("turn");

    await user.click(screen.getByTestId("signing-image-draw"));
    expect(screen.getByTestId("signing-draw-done")).toBeDisabled();
    const canvas = screen.getByTestId("signing-draw-canvas");
    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 10 });
    fireEvent.pointerMove(canvas, { clientX: 60, clientY: 30 });
    fireEvent.pointerUp(canvas);
    await user.click(screen.getByTestId("signing-image-remember"));
    await user.click(screen.getByTestId("signing-draw-done"));

    await waitFor(() => {
      expect(screen.getByTestId("signing-image-ready")).toBeInTheDocument();
    });
    expect(profiles.imageOf(ACADEMIC.id)).not.toBeNull();
    expect(primary()).toHaveAttribute("data-blocked", "");
    await user.click(primary());
    await waitFor(() => {
      expect(pageState()).toBe("done");
    });
  });

  it("берёт сохранённую в профиле подпись одним нажатием", async () => {
    const user = userEvent.setup();
    profiles.saveImage(ACADEMIC.id, new Blob(["saved"], { type: "image/png" }));
    const routeId = await sendRoute(true);
    await approveAs(routeId, SUPERVISOR);
    open(routeId, ACADEMIC);
    await user.click(await screen.findByTestId("signing-image-use-saved"));
    await waitFor(() => {
      expect(screen.getByTestId("signing-image-ready")).toBeInTheDocument();
    });
    await user.click(primary());
    await waitFor(() => {
      expect(pageState()).toBe("done");
    });
  });

  it("меняет способ на ЭП из разрешённых точкой", async () => {
    const user = userEvent.setup();
    const key = identities.add(ACADEMIC.id, {
      label: "Ключ Сидорова",
      subject_cn: ACADEMIC.name,
    });
    const routeId = await sendRoute(true);
    await approveAs(routeId, SUPERVISOR);
    open(routeId, ACADEMIC);
    await user.click(await screen.findByTestId("signing-method-detached"));
    // ЭП нужна плашка: данные берутся из ключа Студии тут же.
    expect(primary()).toHaveAttribute("data-blocked", "plate");
    await user.click(await screen.findByTestId(`signing-plate-key-${key.id}`));
    await waitFor(() => {
      expect(screen.getByTestId("signing-plate")).toHaveTextContent(
        `Ключ: ${ACADEMIC.name}, OpenPGP`,
      );
    });
    await user.click(primary());
    // Согласие зафиксировало документы: осталось подписать итоговый PDF тем же ключом.
    await waitFor(() => {
      expect(primary()).toHaveAttribute("data-label", "sign");
    });
    expect(screen.getByTestId("signing-key-line")).toHaveTextContent(
      "Ключ: Ключ Сидорова",
    );
    await user.click(primary());
    await waitFor(() => {
      expect(pageState()).toBe("done");
    });
    me = ACADEMIC;
    const task = await signingTaskApi.get(PROJECT, routeId);
    expect(task.me.method).toBe("detached");
  });
});

describe("ЭП ключом Студии", () => {
  it("«Подписать» итоговый PDF спрашивает пароль ключа и показывает отказ", async () => {
    const user = userEvent.setup();
    identities.add(SUPERVISOR.id, {
      label: "Рабочий OpenPGP",
      subject_cn: SUPERVISOR.name,
      protected: true,
    });
    const routeId = await routeAtFinalSign();
    open(routeId, SUPERVISOR);
    await waitFor(() => {
      expect(primary()).toHaveAttribute("data-label", "sign");
    });
    expect(primary()).toHaveTextContent("Подписать");
    await user.click(primary());
    await user.type(await screen.findByTestId("signing-passphrase"), "wrong");
    await user.click(screen.getByTestId("signing-passphrase-submit"));
    expect(
      await screen.findByTestId("signing-passphrase-error"),
    ).toHaveTextContent("Пароль ключа не подошёл.");
    expect(pageState()).toBe("turn");

    await user.clear(screen.getByTestId("signing-passphrase"));
    await user.type(screen.getByTestId("signing-passphrase"), "secret");
    await user.click(screen.getByTestId("signing-passphrase-submit"));
    await waitFor(() => {
      expect(pageState()).toBe("completed");
    });
    expect(screen.queryByTestId("signing-passphrase")).not.toBeInTheDocument();
  });

  it("создаёт ключ OpenPGP на странице и сразу «Согласовать и подписать»", async () => {
    const user = userEvent.setup();
    // Автор картинкой, у научрука плашка известна: документы зафиксированы при отправке.
    const routeId = await sendRoute(false);
    open(routeId, SUPERVISOR);
    await waitFor(() => {
      expect(primary()).toHaveAttribute("data-label", "approve_and_sign");
    });
    expect(primary()).toHaveAttribute("data-blocked", "key");
    await user.click(await screen.findByTestId("signing-key-new"));
    expect(screen.getByLabelText("Имя на плашке")).toHaveValue(SUPERVISOR.name);
    await user.type(screen.getByTestId("signing-key-passphrase"), "secret");
    await user.click(screen.getByTestId("signing-key-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("signing-key-line")).toHaveTextContent(
        `OpenPGP: ${SUPERVISOR.name} (с паролем)`,
      );
    });
    expect(identities.keysOf(SUPERVISOR.id)).toHaveLength(1);

    await user.click(primary());
    await user.type(await screen.findByTestId("signing-passphrase"), "secret");
    await user.click(screen.getByTestId("signing-passphrase-submit"));
    await waitFor(() => {
      expect(pageState()).toBe("completed");
    });
  });

  it("без данных плашки ключ Студии заполняет её и подписывает одним нажатием", async () => {
    const user = userEvent.setup();
    supervisorMember.plate = null;
    identities.add(SUPERVISOR.id, {
      label: "Ключ OpenPGP",
      subject_cn: SUPERVISOR.name,
    });
    const routeId = await sendRoute(false);
    open(routeId, SUPERVISOR);
    await waitFor(() => {
      expect(primary()).toHaveAttribute("data-label", "approve_and_sign");
    });
    expect(screen.queryByTestId("signing-plate")).not.toBeInTheDocument();
    expect(primary()).toHaveAttribute("data-blocked", "");
    await user.click(primary());
    await waitFor(() => {
      expect(pageState()).toBe("completed");
    });
  });

  it("импорт файла без закрытого ключа объясняет, почему не подошёл", async () => {
    const user = userEvent.setup();
    const routeId = await sendRoute(false);
    open(routeId, SUPERVISOR);
    await user.click(await screen.findByTestId("signing-key-import-open"));
    await user.upload(
      screen.getByTestId("signing-key-file-input"),
      new File(["key"], "petrov-public.asc"),
    );
    await user.click(screen.getByTestId("signing-key-submit"));
    expect(
      await screen.findByTestId("signing-inline-failure"),
    ).toHaveTextContent("В файле нет закрытого ключа");
    expect(identities.keysOf(SUPERVISOR.id)).toHaveLength(0);
  });
});

describe("ключи на сервере запрещены", () => {
  it("объясняет и оставляет КриптоПро и готовую подпись", async () => {
    const user = userEvent.setup();
    keysAllowed = false;
    const routeId = await routeAtFinalSign();
    open(routeId, SUPERVISOR);
    await waitFor(() => {
      expect(primary()).toHaveAttribute("data-label", "sign");
    });
    expect(screen.getByTestId("signing-no-server-keys")).toHaveTextContent(
      "не хранит закрытые ключи",
    );
    expect(screen.queryByTestId("signing-way-studio")).not.toBeInTheDocument();
    expect(screen.queryByTestId("signing-key-new")).not.toBeInTheDocument();
    expect(screen.getByTestId("signing-way-cryptopro")).toBeInTheDocument();

    // Способ не выбран: кнопка просит выбрать.
    await user.click(primary());
    expect(screen.getByTestId("signing-ways")).toHaveTextContent(
      "Выберите, чем подписать.",
    );
  });

  it("готовая подпись: плохой файл отклонён, верный завершает маршрут", async () => {
    const user = userEvent.setup();
    keysAllowed = false;
    const routeId = await routeAtFinalSign();
    open(routeId, SUPERVISOR);
    await user.click(await screen.findByTestId("signing-way-file"));
    const slot = "topic_application/supervisor";
    expect(primary()).toHaveAttribute("data-blocked", "files");
    await user.upload(
      screen.getByTestId(`signing-file-pick-${slot}-input`),
      new File(["sig"], "bad.sig"),
    );
    await user.click(primary());
    expect(
      await screen.findByTestId("signing-inline-failure"),
    ).toHaveTextContent("Подпись не подходит к итоговому PDF");
    expect(pageState()).toBe("turn");

    await user.upload(
      screen.getByTestId(`signing-file-pick-${slot}-input`),
      new File(["sig"], "application.pdf.asc"),
    );
    await user.click(primary());
    await waitFor(() => {
      expect(pageState()).toBe("completed");
    });
  });

  it("КриптоПро: согласие, подпись итогового PDF плагином и её загрузка", async () => {
    const user = userEvent.setup();
    keysAllowed = false;
    const routeId = await sendRoute(false);
    open(routeId, SUPERVISOR);
    await user.click(await screen.findByTestId("signing-way-cryptopro"));
    expect(primary()).toHaveAttribute("data-label", "approve_and_sign");
    await user.click(primary());
    await waitFor(() => {
      expect(screen.getByTestId("signing-cryptopro")).toHaveAttribute(
        "data-phase",
        "pick",
      );
    });
    expect(screen.getByTestId("signing-cryptopro")).toHaveTextContent(
      "Петров Пётр Петрович",
    );
    await user.click(screen.getByTestId("signing-cryptopro-submit"));
    await waitFor(() => {
      expect(pageState()).toBe("completed");
    });
    expect(cades.signDetached).toHaveBeenCalledOnce();
    // Документы уже зафиксированы: плашку сертификат не трогает.
    expect(cades.exportCertificatePem).not.toHaveBeenCalled();
  });

  it("до фиксации сертификат КриптоПро заполняет плашку", async () => {
    const user = userEvent.setup();
    keysAllowed = false;
    supervisorMember.plate = null;
    const routeId = await sendRoute(true);
    open(routeId, SUPERVISOR);
    await waitFor(() => {
      expect(primary()).toHaveAttribute("data-blocked", "plate");
    });
    await user.click(screen.getByTestId("signing-plate-cryptopro"));
    await user.click(await screen.findByTestId("signing-cryptopro-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("signing-plate")).toHaveTextContent(
        "сертификат",
      );
    });
    expect(cades.exportCertificatePem).toHaveBeenCalledOnce();
    await user.click(primary());
    await waitFor(() => {
      expect(pageState()).toBe("approved");
    });
  });
});
