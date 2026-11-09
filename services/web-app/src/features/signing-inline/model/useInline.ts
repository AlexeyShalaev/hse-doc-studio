import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import { signatureApi } from "@entities/signature";
import {
  signerProfileApi,
  signerProfileKeys,
  useSignerProfile,
} from "@entities/signer-profile";
import {
  signingIdentityApi,
  signingIdentityKeys,
  useSigningIdentities,
} from "@entities/signing-identity";
import {
  expectedTokens,
  signingFailureOf,
  signingRouteKeys,
  useSetSigningTaskPlate,
  useUploadSigningTaskImage,
  type SigningFailure,
  type SigningTask,
} from "@entities/signing-route";
import {
  CadesError,
  exportCertificatePem,
  signDetached,
  type CadesPlugin,
} from "@features/signature-stamper";
import {
  inlinePlan,
  isCryptoMethod,
  pendingSlots,
  type InlinePlan,
  type PendingSlot,
} from "./inlinePlan";
import type { InlineUi, SigningInlineContext } from "./types";

/** Отказ, который блок находит сам: в файле нет закрытого ключа, подпись не подошла. */
class InlineError extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

const failureOf = (error: unknown): SigningFailure => {
  if (error instanceof InlineError) return { code: error.code, detail: null };
  if (error instanceof CadesError)
    return { code: "cryptopro", detail: error.message };
  const failure = signingFailureOf(error);
  // Не запрос (плагин, холст): пояснение берём из самой ошибки.
  return failure.code === "unknown" &&
    failure.detail === null &&
    error instanceof Error &&
    !(error instanceof ApiError) &&
    error.message !== ""
    ? { code: "unknown", detail: error.message }
    : failure;
};

const pngFile = (blob: Blob): File =>
  new File([blob], "signature.png", { type: "image/png" });

const dataUrl = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      reject(new Error("image read failed"));
    };
    reader.readAsDataURL(blob);
  });

/** Сохранённая в профиле картинка: сам файл и адрес для показа. */
export type SavedImage = { blob: Blob; url: string };

const stem = (name: string): string => name.replace(/\.[^.]+$/, "") || name;

export type KeyCreateInput = {
  name: string;
  email: string;
  passphrase: string;
};
export type KeyImportInput = { file: File; passphrase: string };

/**
 * Данные и действия блока подписи. Его зовут и блок «Как подписать», и главная кнопка:
 * выбор и занятость общие (`ui`), запросы идут через кэш задачи.
 */
export const useInline = (ctx: SigningInlineContext, ui: InlineUi) => {
  const { projectId, routeId, task } = ctx;
  const { me } = task;
  const client = useQueryClient();
  const uploadImage = useUploadSigningTaskImage(projectId, routeId);
  const setPlate = useSetSigningTaskPlate(projectId, routeId);

  const cryptoPossible =
    isCryptoMethod(me.method) || me.methods.some(isCryptoMethod);
  const imagePossible = me.method === "image" || me.methods.includes("image");
  // Профиль и ключи читаются только там, где они пригодятся; ошибка чтения не мешает подписи.
  const profile = useSignerProfile(imagePossible && !me.image_ready);
  const savedSha = profile.data?.image?.sha256 ?? null;
  // Картинку читает клиент API (нужна сессия), поэтому показываем её адресом data:.
  const saved = useQuery({
    queryKey: [...signerProfileKeys.all, "image", savedSha],
    queryFn: async (): Promise<SavedImage> => {
      const blob = await signerProfileApi.downloadImage();
      return { blob, url: await dataUrl(blob) };
    },
    enabled: savedSha !== null && imagePossible && !me.image_ready,
    staleTime: Infinity,
    retry: false,
  });
  const identities = useSigningIdentities(
    cryptoPossible && me.keys.server_keys_allowed,
  );

  const plan = inlinePlan(task, ui.state, identities.data);
  const busy = ctx.busy || ui.state.busy;

  /** Одно действие за раз; отказ показывает блок. */
  const guard = async (work: () => Promise<void>): Promise<void> => {
    if (busy) return;
    ui.patch({ busy: true, failure: null, nudge: null });
    try {
      await work();
    } catch (error) {
      ui.patch({ failure: failureOf(error) });
    } finally {
      ui.patch({ busy: false });
    }
  };

  const refreshTask = () =>
    Promise.all([
      client.invalidateQueries({
        queryKey: signingRouteKeys.task(projectId, routeId),
      }),
      client.invalidateQueries({ queryKey: signingRouteKeys.myTasks() }),
    ]);

  // Картинка

  const saveImage = (png: Blob | Promise<Blob>) =>
    guard(async () => {
      const remember = ui.state.remember;
      try {
        await uploadImage.mutateAsync({ file: pngFile(await png), remember });
      } finally {
        // Редактор картинки это окно: отказ под ним не виден, поэтому окно закрываем.
        if (ui.state.panel === "editor") ui.patch({ panel: null });
      }
      if (remember)
        await client.invalidateQueries({ queryKey: signerProfileKeys.all });
      ui.patch({ panel: null });
    });

  /** Сохранённая в профиле подпись: та же загрузка, запоминать её заново незачем. */
  const applySavedImage = () =>
    guard(async () => {
      const blob = saved.data?.blob ?? (await signerProfileApi.downloadImage());
      await uploadImage.mutateAsync({ file: pngFile(blob), remember: false });
    });

  // Плашка

  const plateFromKey = (identityId: string) =>
    guard(async () => {
      await setPlate.mutateAsync({ identityId });
      ui.patch({
        identityId,
        plateKeyId: identityId,
        moreOpen: false,
        panel: null,
      });
    });

  const plateFromFile = (file: File) =>
    guard(async () => {
      await setPlate.mutateAsync({ file });
      ui.patch({ moreOpen: false, panel: null });
    });

  const certificateFile = async (
    api: CadesPlugin,
    thumbprint: string,
  ): Promise<File> =>
    new File([await exportCertificatePem(api, thumbprint)], "certificate.pem", {
      type: "application/x-pem-file",
    });

  const plateFromCryptoPro = (api: CadesPlugin, thumbprint: string) =>
    guard(async () => {
      await setPlate.mutateAsync({
        file: await certificateFile(api, thumbprint),
      });
      ui.patch({ moreOpen: false, prompt: null, way: "cryptopro" });
    });

  // Ключ Студии

  /** Новый ключ сразу выбран для подписи и, пока плашку можно менять, заполняет её. */
  const adoptKey = async (identityId: string) => {
    await client.invalidateQueries({ queryKey: signingIdentityKeys.all });
    ui.patch({ identityId, way: "studio", panel: null, moreOpen: false });
    if (plan?.block === "esign" && plan.canSetPlate) {
      await setPlate.mutateAsync({ identityId });
      ui.patch({ plateKeyId: identityId });
    }
  };

  const createKey = (input: KeyCreateInput) =>
    guard(async () => {
      const identity = await signingIdentityApi.generateOpenPgp(
        {
          name: input.name.trim(),
          email: input.email.trim(),
          passphrase: input.passphrase,
        },
        { silent: true },
      );
      await adoptKey(identity.id);
    });

  const importKey = (input: KeyImportInput) =>
    guard(async () => {
      const passphrase = input.passphrase === "" ? undefined : input.passphrase;
      const identity = /\.(p12|pfx)$/i.test(input.file.name)
        ? await signingIdentityApi.importPkcs12(
            stem(input.file.name),
            input.file,
            passphrase,
            { silent: true },
          )
        : (
            await signingIdentityApi.importOpenPgp(
              input.file,
              passphrase,
              undefined,
              { silent: true },
            )
          ).identities[0];
      // Открытый ключ без закрытой части подписать не может: он годится только для плашки.
      if (!identity) throw new InlineError("no_secret_key");
      await adoptKey(identity.id);
    });

  // Подпись

  /**
   * Открепленные подписи своих слотов по итоговому PDF существующим адресом
   * `.../detached/{slot}`; сервер сверяет очередь и пересчитывает маршрут (раздел 6.10).
   */
  const attachSignatures = async (
    current: SigningTask,
    make: (slot: PendingSlot) => Promise<File | undefined>,
  ): Promise<void> => {
    // Согласовал до фиксации: итогового PDF ещё нет, подпись попросят позже.
    if (current.me.next_action !== "sign") return;
    try {
      for (const slot of pendingSlots(current)) {
        if (!slot.frozen) continue;
        const file = await make(slot);
        if (!file) continue;
        const result = await signatureApi.attachDetached(
          projectId,
          slot.docId,
          slot.slotId,
          file,
          undefined,
          { silent: true },
        );
        if (result.signature.verdict === "invalid")
          throw new InlineError("signature_invalid");
      }
    } finally {
      await refreshTask();
    }
  };

  const approveOnly = (current: InlinePlan) =>
    guard(async () => {
      await ctx.approve({ method: current.methodChange });
    });

  const signWithKey = (current: InlinePlan, passphrase: string | null) =>
    guard(async () => {
      if (!current.key) return;
      const key = { identity_id: current.key.id, passphrase };
      let done: SigningTask | null;
      if (current.action === "sign") {
        done = await ctx.sign(key);
      } else {
        // Плашка должна показывать тот ключ, которым подписывают: без данных или с ключом,
        // выбранным здесь, сначала заполняем её, и отпечатки берём уже из ответа.
        const stale =
          me.plate === null ||
          (ui.state.identityId !== null &&
            ui.state.plateKeyId !== current.key.id);
        const fresh =
          current.canSetPlate && stale
            ? expectedTokens(
                await setPlate.mutateAsync({ identityId: current.key.id }),
              )
            : undefined;
        done = await ctx.approve({
          method: current.methodChange,
          sign: key,
          ...(fresh ? { expected: fresh } : {}),
        });
      }
      // Отказ (например, пароль не подошёл) оставляет окно пароля открытым.
      if (done) ui.patch({ prompt: null });
    });

  const signWithCryptoPro = (api: CadesPlugin, thumbprint: string) =>
    guard(async () => {
      if (!plan) return;
      let current = task;
      if (plan.action !== "sign") {
        let fresh: Record<string, string> | undefined;
        if (plan.canSetPlate) {
          fresh = expectedTokens(
            await setPlate.mutateAsync({
              file: await certificateFile(api, thumbprint),
            }),
          );
        }
        const approved = await ctx.approve({
          method: plan.methodChange,
          ...(fresh ? { expected: fresh } : {}),
        });
        if (!approved) {
          ui.patch({ prompt: null });
          return;
        }
        current = approved;
      }
      await attachSignatures(current, async (slot) => {
        const pdf = await signatureApi.downloadFrozenPdf(
          projectId,
          slot.docId,
          { silent: true },
        );
        const signature = await signDetached(api, thumbprint, pdf);
        // TS 6: Uint8Array<ArrayBufferLike> не BlobPart; копия даёт ArrayBuffer.
        return new File([new Uint8Array(signature)], "signature.sig", {
          type: "application/octet-stream",
        });
      });
      ui.patch({ prompt: null });
    });

  const signWithFiles = (current: InlinePlan) =>
    guard(async () => {
      let next = task;
      if (current.action !== "sign") {
        const approved = await ctx.approve({ method: current.methodChange });
        if (!approved) return;
        next = approved;
      }
      const files = ui.state.files;
      await attachSignatures(next, (slot) => Promise.resolve(files[slot.key]));
      ui.patch({ files: {} });
    });

  /** Главная кнопка: чего-то не хватает, показываем где; иначе действие по выбранному способу. */
  const runPrimary = (): void => {
    if (!plan || busy) return;
    if (plan.blocker !== null) {
      ui.patch({ nudge: plan.blocker, failure: null });
      return;
    }
    if (!plan.needsSign || plan.signAfterFreeze) {
      void approveOnly(plan);
      return;
    }
    if (plan.way === "studio") {
      if (plan.key?.protected) ui.patch({ prompt: "passphrase", nudge: null });
      else void signWithKey(plan, null);
      return;
    }
    if (plan.way === "cryptopro") {
      ui.patch({ prompt: "cryptopro-sign", nudge: null });
      return;
    }
    void signWithFiles(plan);
  };

  return {
    plan,
    busy,
    savedImage: saved.data ?? null,
    keysLoading: identities.isLoading,
    saveImage,
    applySavedImage,
    plateFromKey,
    plateFromFile,
    plateFromCryptoPro,
    createKey,
    importKey,
    signWithKey,
    signWithCryptoPro,
    runPrimary,
  };
};

export type InlineModel = ReturnType<typeof useInline>;
