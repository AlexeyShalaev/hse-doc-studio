import { demoError, demoJson, type DemoRoute } from "@shared/api/demo";
import type { SignerProfile } from "../api/signerProfileSchemas";

// Профиль подписанта для серверного демо и тестов: сохранённая картинка подписи.
// Состояние в памяти, по пользователям; формы тел как у /account/signer-profile.

export type SignerProfileDemoOptions = {
  /** Кто сейчас вошёл; null: 401. */
  getUser: () => { id: string } | null;
  now?: () => number;
};

export type SignerProfileDemo = {
  routes: DemoRoute[];
  reset: () => void;
  /** Сохранить картинку в профиль: «Запомнить для других проектов» и заготовки сценариев. */
  saveImage: (userId: string, image: Blob) => void;
  imageOf: (userId: string) => Blob | null;
};

export const createSignerProfileDemo = (
  options: SignerProfileDemoOptions,
): SignerProfileDemo => {
  const clock = options.now ?? (() => Date.now());
  let images = new Map<string, { blob: Blob; at: string; rev: number }>();
  let rev = 0;

  const saveImage = (userId: string, blob: Blob) => {
    rev += 1;
    images.set(userId, { blob, at: new Date(clock()).toISOString(), rev });
  };

  const profile = (userId: string): SignerProfile => {
    const image = images.get(userId);
    return {
      image: image
        ? {
            sha256: String(image.rev).padStart(64, "0"),
            size: image.blob.size,
            width_px: null,
            height_px: null,
            updated_at: image.at,
          }
        : null,
      public_key: null,
    };
  };

  const signedIn =
    (
      handler: (
        userId: string,
        body: unknown,
      ) => ReturnType<DemoRoute["handler"]>,
    ): DemoRoute["handler"] =>
    (req) => {
      const user = options.getUser();
      return user
        ? handler(user.id, req.body)
        : demoError(401, "auth_required", "Authentication required");
    };

  const routes: DemoRoute[] = [
    {
      method: "GET",
      pattern: "/account/signer-profile",
      handler: signedIn((userId) => demoJson(profile(userId))),
    },
    {
      method: "GET",
      pattern: "/account/signer-profile/image",
      handler: signedIn((userId) => {
        const image = images.get(userId);
        return image
          ? demoJson(image.blob)
          : demoError(404, "not_found", "Not Found");
      }),
    },
    {
      method: "PUT",
      pattern: "/account/signer-profile/image",
      handler: signedIn((userId, body) => {
        const file =
          typeof FormData !== "undefined" && body instanceof FormData
            ? body.get("file")
            : null;
        if (!(file instanceof Blob))
          return demoError(422, "validation_error", "file is required");
        saveImage(userId, file);
        return demoJson(profile(userId));
      }),
    },
    {
      method: "DELETE",
      pattern: "/account/signer-profile/image",
      handler: signedIn((userId) => {
        images.delete(userId);
        return demoJson(profile(userId));
      }),
    },
  ];

  return {
    routes,
    reset: () => {
      images = new Map();
      rev = 0;
    },
    saveImage,
    imageOf: (userId) => images.get(userId)?.blob ?? null,
  };
};
