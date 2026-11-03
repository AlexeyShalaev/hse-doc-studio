// Собирает справку по разу на аудиторию: в каждой сборке только то, что ей положено читать.
//
// Спрятать ссылки в меню мало: страница осталась бы доступна по адресу, а её текст лежал бы в
// индексе Pagefind, и поиск процитировал бы его любому. Поэтому статьи вырезаются из копии src ДО
// сборки: в сборке `user` статьи администратора нет ни в навигации, ни в поиске, ни по адресу.
//
// Медиа общие и лежат один раз: dist/media (кадры админки не секрет, а копия на аудиторию удвоила бы образ).
// Какую сборку отдать, решает сервер Студии (services/api, маршрут /help/).
import {cpSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, unlinkSync} from 'node:fs'
import {dirname, join, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {spawnSync} from 'node:child_process'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RANK = {user: 0, admin: 1}
const AUDIENCES = process.env.DOCS_AUDIENCES?.split(',') ?? Object.keys(RANK)
const ACCESS = /^---\r?\n[\s\S]*?\baccess:\s*['"]?([a-z]+)['"]?\s*$/m

const walk = (dir) =>
  readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })

let failed = false
rmSync(join(ROOT, 'dist'), {recursive: true, force: true})

for (const audience of AUDIENCES) {
  if (!(audience in RANK)) throw new Error(`Неизвестная аудитория "${audience}"`)
  const stage = join(ROOT, '.build', audience)
  rmSync(stage, {recursive: true, force: true})
  mkdirSync(stage, {recursive: true})
  cpSync(join(ROOT, 'src'), join(stage, 'src'), {recursive: true})

  let kept = 0
  let pruned = 0
  for (const file of walk(join(stage, 'src', 'content', 'docs'))) {
    if (!/\.mdx?$/.test(file)) continue
    const match = ACCESS.exec(readFileSync(file, 'utf-8'))
    if (!match || !(match[1] in RANK)) {
      console.error(`НЕТ access (user|admin): ${file.slice(stage.length + 1)}`)
      failed = true
      unlinkSync(file)
      continue
    }
    if (RANK[match[1]] > RANK[audience]) {
      unlinkSync(file)
      pruned++
    } else kept++
  }

  const result = spawnSync(process.execPath, [join(ROOT, 'node_modules', 'astro', 'bin', 'astro.mjs'), 'build'], {
    cwd: ROOT,
    stdio: 'inherit',
    env: {...process.env, DOCS_SRC_DIR: join(stage, 'src'), DOCS_OUT_DIR: join(ROOT, 'dist', audience), DOCS_AUDIENCE: audience},
  })
  if (result.status !== 0) throw new Error(`astro build упал для аудитории "${audience}"`)

  const media = join(ROOT, 'dist', audience, 'media')
  if (existsSync(media)) {
    if (!existsSync(join(ROOT, 'dist', 'media'))) renameSync(media, join(ROOT, 'dist', 'media'))
    else rmSync(media, {recursive: true, force: true})
  }
  console.log(`собрано ${audience}: статей ${kept}, скрыто ${pruned}`)
}

if (failed) process.exit(1)
