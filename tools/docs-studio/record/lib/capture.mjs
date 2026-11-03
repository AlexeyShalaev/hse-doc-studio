// Ролик дубля: кадры CDP-скринкаста с реальными отметками времени, собранные ffmpeg.
//
// Не `recordVideo`: встроенный рекордер Playwright пишет VP8 в CSS-размере и мылит текст.
// Кадры приходят, только когда что-то изменилось, поэтому каждый держится до следующего: список
// ffconcat с длительностями даёт правильный хронометраж. Длинная пауза (загрузка PDF) сжимается
// до MAX_HOLD, чтобы ролик не стоял на одном кадре.
import {mkdir, rm, writeFile} from 'node:fs/promises'
import {spawn} from 'node:child_process'
import {join} from 'node:path'

const LAST_HOLD = 1.2
const MAX_HOLD = 2.5

export async function startCapture(page, framesDir, {width, height, scale}) {
  await rm(framesDir, {recursive: true, force: true})
  await mkdir(framesDir, {recursive: true})
  const cdp = await page.context().newCDPSession(page)
  const cap = {cdp, framesDir, count: 0, stamps: [], stopped: false, pending: [], marks: []}
  cdp.on('Page.screencastFrame', (frame) => {
    if (!cap.stopped) {
      const i = cap.count++
      cap.pending.push(writeFile(join(framesDir, `f${String(i).padStart(6, '0')}.jpg`), Buffer.from(frame.data, 'base64')))
      cap.stamps.push(Date.now() / 1000)
    }
    cdp.send('Page.screencastFrameAck', {sessionId: frame.sessionId}).catch(() => {})
  })
  await cdp.send('Page.startScreencast', {format: 'jpeg', quality: 92, everyNthFrame: 1, maxWidth: width * scale, maxHeight: height * scale})
  return cap
}

/** Отметка начала шага: индекс следующего кадра, в секунды её переводит stopCapture. */
export const mark = (cap) => cap.marks.push(cap.count)

export async function stopCapture(cap, {base, width}) {
  cap.stopped = true
  await cap.cdp.send('Page.stopScreencast').catch(() => {})
  await cap.cdp.detach().catch(() => {})
  await Promise.all(cap.pending)
  if (cap.count === 0) throw new Error('ни одного кадра: страница не отрисовалась')
  const lines = ['ffconcat version 1.0']
  const startsAt = [0]
  for (let i = 0; i < cap.count; i++) {
    const next = cap.stamps[i + 1]
    const hold = next === undefined ? LAST_HOLD : Math.min(Math.max(next - cap.stamps[i], 1 / 60), MAX_HOLD)
    lines.push(`file 'f${String(i).padStart(6, '0')}.jpg'`, `duration ${hold.toFixed(4)}`)
    startsAt.push(startsAt[i] + hold)
  }
  // ffconcat требует повторить последний файл, иначе его длительность теряется.
  lines.push(`file 'f${String(cap.count - 1).padStart(6, '0')}.jpg'`)
  const list = join(cap.framesDir, 'list.ffconcat')
  await writeFile(list, lines.join('\n') + '\n')
  const vf = `fps=24,scale=${width}:-2:flags=lanczos`
  // Один формат: MP4 (H.264, yuv420p, faststart) играют все браузеры, включая Safari.
  await ffmpeg(['-y', '-f', 'concat', '-safe', '0', '-i', list, '-vf', vf, '-c:v', 'libx264', '-crf', '26', '-preset', 'slow',
    '-tune', 'stillimage', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', `${base}.mp4`])
  await rm(cap.framesDir, {recursive: true, force: true})
  return {seconds: startsAt[cap.count], chapters: cap.marks.map((i) => Number(startsAt[Math.min(i, cap.count)].toFixed(1)))}
}

/** Постер: кадр ролика в момент `at` (PNG без потерь), дальше его жмёт в WebP media.mjs. */
export async function posterPng(video, out, at) {
  await ffmpeg(['-y', '-ss', at.toFixed(2), '-i', video, '-frames:v', '1', out])
}

export function ffmpeg(args) {
  return new Promise((resolve, reject) => {
    const child = spawn('ffmpeg', ['-loglevel', 'error', ...args], {stdio: ['ignore', 'inherit', 'inherit']})
    child.on('exit', (code) => (code === 0 ? resolve() : reject(new Error(`ffmpeg завершился с кодом ${code}`))))
    child.on('error', reject)
  })
}
