import { describe, expect, it } from "vitest";
import { MAX_PEM_BYTES, pemCount, pemProblem } from "./pem";

const CERT = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----";

describe("pemProblem", () => {
  it("принимает сертификат и цепочку", () => {
    expect(pemProblem(CERT)).toBeNull();
    expect(pemProblem(`\n${CERT}\n${CERT}\n`)).toBeNull();
    expect(pemCount(`${CERT}\n${CERT}`)).toBe(2);
  });

  it("отсекает пустое, закрытый ключ, чужой текст и слишком большой файл", () => {
    expect(pemProblem("   ")).toBe("empty");
    expect(
      pemProblem(
        "-----BEGIN RSA PRIVATE KEY-----\nx\n-----END RSA PRIVATE KEY-----",
      ),
    ).toBe("private_key");
    // Ключ внутри цепочки тоже не пускаем.
    expect(
      pemProblem(
        `${CERT}\n-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----`,
      ),
    ).toBe("private_key");
    expect(pemProblem("hello")).toBe("not_pem");
    expect(pemProblem(`${CERT}${"a".repeat(MAX_PEM_BYTES)}`)).toBe("too_large");
  });
});
