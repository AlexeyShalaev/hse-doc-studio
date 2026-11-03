// Ни в кадре, ни в ролике не должно быть имени пользователя машины, на которой снимали, и пути
// к его домашнему каталогу: справка уезжает в репозиторий и в образ. Проверяется видимый текст
// страницы, значения полей ввода и заголовок; при совпадении дубль падает, медиа не пишется.
import {homedir, userInfo} from 'node:os'

const MARKERS = [...new Set([userInfo().username, homedir()].filter((m) => m && m.length >= 3))]

export async function assertNoPersonalData(page, where) {
  const text = await page.evaluate(() => {
    const fields = [...document.querySelectorAll('input, textarea')].map((el) => el.value)
    return [document.title, document.body?.innerText ?? '', ...fields].join('\n')
  })
  const lower = text.toLowerCase()
  const hit = MARKERS.find((m) => lower.includes(m.toLowerCase()))
  if (hit) throw new Error(`в кадре личные данные машины («${hit}»): ${where}`)
}
