// Проверка текста сертификата перед отправкой: полноценный разбор делает сервер,
// здесь отсекаем очевидное (закрытый ключ, не тот файл, слишком большой файл),
// чтобы человек увидел причину сразу.

export const MAX_PEM_BYTES = 64 * 1024;

export type PemProblem = "empty" | "private_key" | "not_pem" | "too_large";

const BEGIN = "-----BEGIN CERTIFICATE-----";
const END = "-----END CERTIFICATE-----";

export const pemProblem = (text: string): PemProblem | null => {
  const value = text.trim();
  if (value === "") return "empty";
  if (value.length > MAX_PEM_BYTES) return "too_large";
  // Закрытый ключ сюда попасть не должен ни при каких обстоятельствах.
  if (value.includes("PRIVATE KEY-----")) return "private_key";
  if (!value.includes(BEGIN) || !value.includes(END)) return "not_pem";
  return null;
};

/** Сколько сертификатов в тексте (цепочка из файла считается целиком). */
export const pemCount = (text: string): number => text.split(BEGIN).length - 1;

/** Читает выбранный файл как текст; FileReader работает и там, где нет File.text(). */
export const readFileText = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      reject(new Error("read failed"));
    };
    reader.readAsText(file.slice(0, MAX_PEM_BYTES + 1));
  });
