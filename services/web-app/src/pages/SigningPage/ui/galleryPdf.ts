// Образец PDF для галереи страницы подписанта: настоящий одностраничный A4, который pdf.js
// читает без сервера. Строки подписей стоят там же, где слоты эталонов задачи
// (научрук 110x130 мм, академрук 110x160 мм, студент 120x230 мм), чтобы рамки «Ваша
// подпись» легли на свои места. Только для галереи разработчика.

const MM = 72 / 25.4;
const PAGE_H = 842;

/** Строка текста: x и y в мм от левого верхнего угла, как у слотов. */
const line = (xMm: number, yMm: number, size: number, text: string) =>
  `BT /F1 ${String(size)} Tf ${(xMm * MM).toFixed(1)} ${(PAGE_H - yMm * MM).toFixed(1)} Td (${text}) Tj ET`;

const content = [
  line(70, 30, 14, "APPLICATION"),
  line(48, 38, 11, "for approval of the course project topic"),
  line(25, 60, 10, "Student: Ivanov I. I., group BPI-231"),
  line(25, 68, 10, "Topic: Bertie, an assistant that writes to organizations"),
  line(25, 76, 10, "Supervisor: Petrov P. P."),
  line(25, 132, 10, "Supervisor"),
  line(110, 145, 8, "______________________________"),
  line(25, 162, 10, "Academic supervisor"),
  line(110, 175, 8, "______________________________"),
  line(25, 232, 10, "Student"),
  line(120, 245, 8, "______________________________"),
].join("\n");

const buildPdf = (): string => {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>",
    `<< /Length ${String(content.length)} >>\nstream\n${content}\nendstream`,
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${String(index + 1)} 0 obj\n${object}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${String(objects.length + 1)}\n0000000000 65535 f \n`;
  for (const offset of offsets)
    body += `${String(offset).padStart(10, "0")} 00000 n \n`;
  body += `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\nstartxref\n${String(xref)}\n%%EOF\n`;
  return body;
};

let url: string | null = null;

/** Адрес образца (blob:), один на вкладку. */
export const galleryPdfUrl = (): string => {
  url ??= URL.createObjectURL(
    new Blob([buildPdf()], { type: "application/pdf" }),
  );
  return url;
};
