import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { i18n } from "@shared/lib";
import {
  LOCAL_BOOTSTRAP,
  sessionKeys,
  type Bootstrap,
} from "@entities/session";
import type { SignerProfile } from "@entities/signer-profile";
import { SigningIdentitiesSection } from "./SigningIdentitiesSection";
import { SignerProfileBlock } from "./SignerProfileBlock";

const EMPTY: SignerProfile = { image: null, public_key: null };

const FULL: SignerProfile = {
  image: {
    sha256: "a".repeat(64),
    size: 1200,
    width_px: 300,
    height_px: 100,
    updated_at: "2026-11-09T10:00:00+00:00",
  },
  public_key: {
    kind: "openpgp",
    owner: "Пётр Петров",
    cert_id: "1A2B 3C4D 5E6F 7A8B",
    valid_from: "2026-01-01T00:00:00+00:00",
    valid_to: null,
    signer_id: "F".repeat(40),
    level: "",
    updated_at: "2026-11-09T10:00:00+00:00",
  },
};

const SERVER_USER: Bootstrap = {
  ...LOCAL_BOOTSTRAP,
  mode: "server",
  user: {
    id: "u1",
    name: "Пётр Петров",
    email: "petrov@example.org",
    avatar_initials: "ПП",
    is_instance_admin: false,
    email_verified: true,
    locale: "ru",
    org_roles: [],
  },
  capabilities: {
    ...LOCAL_BOOTSTRAP.capabilities,
    docker_ui: false,
    local_services_ui: false,
    personal_signing_keys: false,
  },
};

const mount = (
  ui: React.ReactNode,
  bootstrap: Bootstrap,
  profile: SignerProfile,
) => {
  const get = vi
    .spyOn(apiClient, "get")
    .mockImplementation((url: string) =>
      url === "/account/signer-profile"
        ? Promise.resolve({ data: profile })
        : Promise.reject(new ApiError("off", "unknown_error", 500)),
    );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(sessionKeys.bootstrap(), bootstrap);
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
    </QueryClientProvider>,
  );
  return get;
};

describe("SignerProfileBlock", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("empty profile: says nothing is saved and offers uploads", async () => {
    mount(<SignerProfileBlock />, SERVER_USER, EMPTY);

    expect(
      await screen.findByText(i18n.t("settings:signing.profile.imageEmpty")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(i18n.t("settings:signing.profile.keyEmpty")),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", {
        name: i18n.t("settings:signing.profile.upload"),
      }),
    ).toHaveLength(2);
  });

  it("saved profile: shows the image and the plate owner with the key id", async () => {
    mount(<SignerProfileBlock />, SERVER_USER, FULL);

    const image = await screen.findByAltText(
      i18n.t("settings:signing.profile.imageAlt"),
    );
    expect(image.getAttribute("src")).toContain(
      "/api/v1/account/signer-profile/image?v=aaaaaaaaaaaaaaaa",
    );
    expect(screen.getByText("Пётр Петров")).toBeInTheDocument();
    expect(screen.getByText("1A2B 3C4D 5E6F 7A8B")).toBeInTheDocument();
    expect(
      screen.getByText(i18n.t("settings:signing.profile.kindOpenpgp")),
    ).toBeInTheDocument();
  });

  it("picking a PNG uploads it as multipart and shows the saved image", async () => {
    mount(<SignerProfileBlock />, SERVER_USER, EMPTY);
    const put = vi
      .spyOn(apiClient, "put")
      .mockResolvedValue({ data: { ...EMPTY, image: FULL.image } });
    await screen.findByText(i18n.t("settings:signing.profile.imageEmpty"));

    const file = new File(["png"], "sign.png", { type: "image/png" });
    fireEvent.change(screen.getByTestId("signer-profile-image-input"), {
      target: { files: [file] },
    });

    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const [url, body] = put.mock.calls[0] ?? [];
    expect(url).toBe("/account/signer-profile/image");
    expect(body).toBeInstanceOf(FormData);
    expect(
      await screen.findByAltText(i18n.t("settings:signing.profile.imageAlt")),
    ).toBeInTheDocument();
  });

  it("refused private key: the server message is shown, the profile stays empty", async () => {
    mount(<SignerProfileBlock />, SERVER_USER, EMPTY);
    vi.spyOn(apiClient, "put").mockRejectedValue(
      new ApiError("В файле закрытый ключ", "unknown_error", 400),
    );
    await screen.findByText(i18n.t("settings:signing.profile.keyEmpty"));

    fireEvent.change(screen.getByTestId("signer-profile-key-input"), {
      target: { files: [new File(["k"], "key.pem")] },
    });

    expect(
      await screen.findByText(i18n.t("settings:signing.profile.keyEmpty")),
    ).toBeInTheDocument();
  });
});

describe("SigningIdentitiesSection: signer profile", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("server with an account: the profile block is shown even when keys are forbidden", async () => {
    mount(<SigningIdentitiesSection />, SERVER_USER, EMPTY);

    expect(await screen.findByTestId("signer-profile")).toBeInTheDocument();
    expect(screen.getByTestId("signing-forbidden")).toBeInTheDocument();
  });

  it("local Studio: no profile block and no profile request", () => {
    const get = mount(<SigningIdentitiesSection />, LOCAL_BOOTSTRAP, EMPTY);

    expect(screen.queryByTestId("signer-profile")).not.toBeInTheDocument();
    expect(get).not.toHaveBeenCalledWith("/account/signer-profile");
  });
});
