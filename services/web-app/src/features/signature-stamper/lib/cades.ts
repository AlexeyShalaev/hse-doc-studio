// КриптоПро ЭЦП Browser plug-in: список сертификатов и открепленная подпись CAdES-BES.
//
// Закрытый ключ УКЭП лежит на токене под КриптоПро CSP и не покидает его: подпись
// делает плагин в браузере пользователя, Студия получает готовый файл. Сам плагин
// открывается скриптом cadesplugin_api.js: берём копию из папки данных Студии (если
// пользователь её положил) либо с сайта КриптоПро.

import { env } from "@shared/config";

// Константы CAPICOM / CAdES COM.
const CAPICOM_CURRENT_USER_STORE = 2;
const CAPICOM_MY_STORE = "My";
const CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED = 2;
const CAPICOM_CERTIFICATE_FIND_TIME_VALID = 9;
const CAPICOM_ENCODE_BASE64 = 0;
const CADESCOM_BASE64_TO_BINARY = 1;
const CADESCOM_CADES_BES = 1;

const OFFICIAL_API_URL =
  "https://www.cryptopro.ru/sites/default/files/products/cades/cadesplugin_api.js";
const LOAD_TIMEOUT_MS = 8000;

// Минимум от асинхронного COM-прокси плагина, который нам нужен. Свойства и методы
// объектов плагина возвращают промисы, а запись свойства идёт через `propset_*`.
export type CadesObject = Record<string, unknown>;
export type CadesPlugin = {
  CreateObjectAsync: (name: string) => Promise<CadesObject>;
};

export type CadesCertificate = {
  thumbprint: string;
  subject: string; // CN
  issuer: string; // CN
  validFrom: Date;
  validTo: Date;
  hasPrivateKey: boolean;
};

export class CadesError extends Error {
  constructor(
    readonly code: "not-loaded" | "no-plugin" | "no-certs" | "failed",
    message: string,
  ) {
    super(message);
  }
}

const cnOf = (dn: string): string => {
  const m = /(?:^|,\s*)CN=("(?:[^"]|"")*"|[^,]*)/.exec(dn);
  return m?.[1] ? m[1].replace(/^"|"$/g, "").replace(/""/g, '"') : dn;
};

const get = async <T>(obj: unknown, prop: string): Promise<T> =>
  (await (obj as Record<string, Promise<T>>)[prop]) as T;

const call = async <T>(
  obj: unknown,
  method: string,
  ...args: unknown[]
): Promise<T> =>
  (await (obj as Record<string, (...a: unknown[]) => Promise<T>>)[method]?.(
    ...args,
  )) as T;

const openStore = async (api: CadesPlugin): Promise<CadesObject> => {
  const store = await api.CreateObjectAsync("CAdESCOM.Store");
  await call(
    store,
    "Open",
    CAPICOM_CURRENT_USER_STORE,
    CAPICOM_MY_STORE,
    CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED,
  );
  return store;
};

const validCertificates = async (store: CadesObject): Promise<CadesObject> =>
  call<CadesObject>(
    await get(store, "Certificates"),
    "Find",
    CAPICOM_CERTIFICATE_FIND_TIME_VALID,
  );

const describe = async (cert: CadesObject): Promise<CadesCertificate> => ({
  thumbprint: await get<string>(cert, "Thumbprint"),
  subject: cnOf(await get<string>(cert, "SubjectName")),
  issuer: cnOf(await get<string>(cert, "IssuerName")),
  validFrom: new Date(await get<string>(cert, "ValidFromDate")),
  validTo: new Date(await get<string>(cert, "ValidToDate")),
  hasPrivateKey: Boolean(await call(cert, "HasPrivateKey")),
});

/** Сертификаты текущего пользователя с закрытым ключом, действующие сейчас. */
export const listCertificates = async (
  api: CadesPlugin,
): Promise<CadesCertificate[]> => {
  const store = await openStore(api);
  try {
    const certs = await validCertificates(store);
    const count = Number(await get(certs, "Count"));
    const result: CadesCertificate[] = [];
    for (let i = 1; i <= count; i++) {
      const info = await describe(await call<CadesObject>(certs, "Item", i));
      if (info.hasPrivateKey) result.push(info);
    }
    return result;
  } finally {
    await call(store, "Close");
  }
};

const findCertificate = async (
  api: CadesPlugin,
  thumbprint: string,
): Promise<{ store: CadesObject; cert: CadesObject }> => {
  const store = await openStore(api);
  const certs = await validCertificates(store);
  const count = Number(await get(certs, "Count"));
  for (let i = 1; i <= count; i++) {
    const cert = await call<CadesObject>(certs, "Item", i);
    if ((await get<string>(cert, "Thumbprint")) === thumbprint) {
      return { store, cert };
    }
  }
  await call(store, "Close");
  throw new CadesError("no-certs", "certificate not found in the store");
};

/** Открытая часть сертификата в PEM: из неё Студия берёт данные для плашки. */
export const exportCertificatePem = async (
  api: CadesPlugin,
  thumbprint: string,
): Promise<string> => {
  const { store, cert } = await findCertificate(api, thumbprint);
  try {
    const b64 = String(await call(cert, "Export", CAPICOM_ENCODE_BASE64));
    const body = b64.replace(/\s+/g, "").replace(/(.{64})/g, "$1\n");
    return `-----BEGIN CERTIFICATE-----\n${body}\n-----END CERTIFICATE-----\n`;
  } finally {
    await call(store, "Close");
  }
};

export const bytesToBase64 = (bytes: Uint8Array): string => {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
};

export const base64ToBytes = (b64: string): Uint8Array => {
  const bin = atob(b64.replace(/\s+/g, ""));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
};

/** Открепленная подпись CAdES-BES (DER) файла. Плагин сам спросит PIN токена. */
export const signDetached = async (
  api: CadesPlugin,
  thumbprint: string,
  content: Uint8Array,
): Promise<Uint8Array> => {
  const { store, cert } = await findCertificate(api, thumbprint);
  try {
    const signer = await api.CreateObjectAsync("CAdESCOM.CPSigner");
    await call(signer, "propset_Certificate", cert);
    const data = await api.CreateObjectAsync("CAdESCOM.CadesSignedData");
    await call(data, "propset_ContentEncoding", CADESCOM_BASE64_TO_BINARY);
    await call(data, "propset_Content", bytesToBase64(content));
    const signature = String(
      await call(data, "SignCades", signer, CADESCOM_CADES_BES, true),
    );
    return base64ToBytes(signature);
  } finally {
    await call(store, "Close");
  }
};

// ── Загрузка cadesplugin_api.js ───────────────────────────────────────────────

type CadesWindow = Window & {
  cadesplugin?: Promise<void> & Partial<CadesPlugin>;
};

const injectScript = (src: string): Promise<void> =>
  new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = src;
    el.async = true;
    el.onload = () => {
      resolve();
    };
    el.onerror = () => {
      el.remove();
      reject(new Error(`cannot load ${src}`));
    };
    document.head.appendChild(el);
  });

export const localApiUrl = (): string =>
  `${env.VITE_API_BASE_URL}/api/v1/crypto/cadesplugin_api.js`;

let loading: Promise<CadesPlugin> | null = null;

/** Загружает API плагина и ждёт, пока расширение браузера отзовётся. */
export const loadCadesPlugin = (): Promise<CadesPlugin> => {
  loading ??= (async () => {
    const w = window as CadesWindow;
    if (!w.cadesplugin) {
      try {
        await injectScript(localApiUrl());
      } catch {
        await injectScript(OFFICIAL_API_URL).catch(() => {
          throw new CadesError("not-loaded", "cadesplugin_api.js unavailable");
        });
      }
    }
    const plugin = w.cadesplugin;
    if (!plugin) throw new CadesError("not-loaded", "no cadesplugin object");
    const ready = await Promise.race([
      plugin.then(() => true),
      new Promise<false>((r) => setTimeout(() => r(false), LOAD_TIMEOUT_MS)),
    ]).catch(() => false);
    if (!ready || typeof plugin.CreateObjectAsync !== "function") {
      throw new CadesError("no-plugin", "browser plug-in did not respond");
    }
    return plugin as CadesPlugin;
  })().catch((err: unknown) => {
    loading = null;
    throw err;
  });
  return loading;
};
