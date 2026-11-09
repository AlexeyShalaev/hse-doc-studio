import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";
import { SignerProfileSchema } from "./signerProfileSchemas";

const PATH = "/account/signer-profile";

const upload = (path: string, file: Blob, name: string) => {
  const formData = new FormData();
  formData.append("file", file, name);
  return apiClient
    .put(path, formData, { headers: { "Content-Type": null } })
    .then(parseResp(SignerProfileSchema));
};

export const signerProfileApi = {
  get: () => apiClient.get(PATH).then(parseResp(SignerProfileSchema)),

  /** PNG: загруженный файл или нарисованная подпись (Blob из canvas). */
  saveImage: (file: Blob, name = "signature.png") =>
    upload(`${PATH}/image`, file, name),

  clearImage: () =>
    apiClient.delete(`${PATH}/image`).then(parseResp(SignerProfileSchema)),

  /** Сертификат (.cer, .crt, .pem) или открытый ключ OpenPGP (.asc). */
  savePublicKey: (file: File) => upload(`${PATH}/public-key`, file, file.name),

  clearPublicKey: () =>
    apiClient.delete(`${PATH}/public-key`).then(parseResp(SignerProfileSchema)),
};

/** Адрес картинки; хеш в адресе сбрасывает кеш браузера после замены. */
export const profileImageUrl = (sha256: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1${PATH}/image?v=${sha256.slice(0, 16)}`;
