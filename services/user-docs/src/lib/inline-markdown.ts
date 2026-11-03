/**
 * Тот же минимум разметки, что понимает панель справки в приложении: **жирный**, *курсив*, ссылки.
 * Сначала экранируем, потом размечаем: шаг, где упомянут `<b>`, остаётся текстом.
 */
const escapeHtml = (text: string): string =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export function renderInlineMarkdown(text: string, base = ''): string {
  return escapeHtml(text)
    .replace(/\[([^\]]+)]\(([^)\s]+)\)/g, (_m, label: string, href: string) => {
      const url = href.startsWith('/') && !href.startsWith(base) ? `${base}${href}` : href
      return `<a href="${url}">${label}</a>`
    })
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
}
