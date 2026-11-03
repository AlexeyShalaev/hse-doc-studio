// Битые ссылки в собранной справке (после `pnpm build`): каждая ссылка /help/... на странице сборки
// должна вести в файл ЭТОЙ сборки или в общие медиа. Ссылка из статьи пользователя на статью
// администратора в сборке user тоже битая, и это правильно: читатель её не откроет.
import {existsSync, readFileSync, readdirSync, statSync} from 'node:fs'
import {dirname, join, relative, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'

const DIST = resolve(dirname(fileURLToPath(import.meta.url)), '../dist')
const walk = (dir) => readdirSync(dir).flatMap((e) => (statSync(join(dir, e)).isDirectory() ? walk(join(dir, e)) : [join(dir, e)]))

if (!existsSync(DIST)) {
  console.error('нет dist/: сначала pnpm build')
  process.exit(1)
}
const broken = []
let checked = 0
for (const audience of ['user', 'admin']) {
  const root = join(DIST, audience)
  if (!existsSync(root)) continue
  const resolveTarget = (url) => {
    const path = decodeURI(url.split('#')[0].split('?')[0]).replace(/^\/help\//, '')
    if (path.startsWith('media/')) return existsSync(join(DIST, path))
    const candidates = [join(root, path), join(root, path, 'index.html')]
    return candidates.some((c) => existsSync(c) && statSync(c).isFile())
  }
  for (const file of walk(root).filter((f) => f.endsWith('.html'))) {
    const html = readFileSync(file, 'utf-8')
    for (const [, url] of html.matchAll(/(?:href|src|poster)="(\/help\/[^"]*)"/g)) {
      checked++
      // Медиа проверяет check.mjs (съёмка — отдельная джоба); здесь только страницы и ассеты сайта.
      if (url.startsWith('/help/media/')) continue
      if (!resolveTarget(url)) broken.push(`${audience}/${relative(root, file)} → ${url}`)
    }
  }
}
if (broken.length) {
  for (const b of broken) console.error(`БИТАЯ ССЫЛКА: ${b}`)
  process.exit(1)
}
console.log(`ссылки в порядке: проверено ${checked}`)
