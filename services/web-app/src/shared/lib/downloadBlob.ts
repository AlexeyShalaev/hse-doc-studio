const REVOKE_DELAY_MS = 4000;

// Отдаёт браузеру содержимое как скачиваемый файл с заданным именем.
export const downloadBlob = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // Адрес освобождаем позже: Safari и Firefox могут оборвать большую загрузку.
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, REVOKE_DELAY_MS);
};
