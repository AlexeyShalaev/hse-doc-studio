import { describe, expect, it } from "vitest";
import {
  base64ToBytes,
  bytesToBase64,
  exportCertificatePem,
  listCertificates,
  signDetached,
  type CadesObject,
  type CadesPlugin,
} from "./cades";

// Асинхронный COM-прокси плагина: свойства и методы возвращают промисы.
const makeCert = (thumb: string, cn: string, hasKey = true) =>
  ({
    Thumbprint: Promise.resolve(thumb),
    SubjectName: Promise.resolve(`SN=Иванов, CN="${cn}", O=ВШЭ`),
    IssuerName: Promise.resolve("CN=УЦ Тест"),
    ValidFromDate: Promise.resolve("2026-04-21T09:13:14.000Z"),
    ValidToDate: Promise.resolve("2027-04-21T09:23:14.000Z"),
    HasPrivateKey: () => Promise.resolve(hasKey),
    Export: () => Promise.resolve("QUJD\nREVG"),
  }) as unknown as CadesObject;

const makePlugin = (certs: CadesObject[]) => {
  const log: string[] = [];
  const plugin: CadesPlugin = {
    CreateObjectAsync: (name) => {
      if (name === "CAdESCOM.Store") {
        return Promise.resolve({
          Open: () => Promise.resolve(log.push("open")),
          Close: () => Promise.resolve(log.push("close")),
          Certificates: Promise.resolve({
            Find: () =>
              Promise.resolve({
                Count: Promise.resolve(certs.length),
                Item: (i: number) => Promise.resolve(certs[i - 1]),
              }),
          }),
        } as unknown as CadesObject);
      }
      if (name === "CAdESCOM.CPSigner") {
        return Promise.resolve({
          propset_Certificate: () => Promise.resolve(log.push("signer-cert")),
        } as unknown as CadesObject);
      }
      return Promise.resolve({
        propset_ContentEncoding: () => Promise.resolve(),
        propset_Content: (b64: string) =>
          Promise.resolve(log.push(`content:${b64}`)),
        SignCades: (_s: unknown, type: number, detached: boolean) =>
          Promise.resolve(log.push(`sign:${type}:${detached}`) && "AQID\nBA=="),
      } as unknown as CadesObject);
    },
  };
  return { plugin, log };
};

describe("cades client", () => {
  it("lists only certificates with a private key and reads the CN", async () => {
    const { plugin, log } = makePlugin([
      makeCert("AA", "Иванов Иван"),
      makeCert("BB", "Без ключа", false),
    ]);
    const list = await listCertificates(plugin);
    expect(list.map((c) => c.thumbprint)).toEqual(["AA"]);
    expect(list[0]?.subject).toBe("Иванов Иван");
    expect(list[0]?.issuer).toBe("УЦ Тест");
    expect(log.at(-1)).toBe("close");
  });

  it("exports a certificate as PEM", async () => {
    const { plugin } = makePlugin([makeCert("AA", "Иванов")]);
    const pem = await exportCertificatePem(plugin, "AA");
    expect(pem).toBe(
      "-----BEGIN CERTIFICATE-----\nQUJDREVG\n-----END CERTIFICATE-----\n",
    );
  });

  it("signs detached CAdES-BES and decodes the base64 result", async () => {
    const { plugin, log } = makePlugin([makeCert("AA", "Иванов")]);
    const sig = await signDetached(plugin, "AA", new Uint8Array([1, 2, 3]));
    expect([...sig]).toEqual([1, 2, 3, 4]);
    expect(log).toContain("sign:1:true");
    expect(log).toContain(
      `content:${bytesToBase64(new Uint8Array([1, 2, 3]))}`,
    );
  });

  it("fails clearly when the certificate disappeared", async () => {
    const { plugin } = makePlugin([makeCert("AA", "Иванов")]);
    await expect(signDetached(plugin, "ZZ", new Uint8Array())).rejects.toThrow(
      /not found/,
    );
  });

  it("round-trips base64", () => {
    const bytes = new Uint8Array(70000).map((_, i) => i % 251);
    expect(base64ToBytes(bytesToBase64(bytes))).toEqual(bytes);
  });
});
