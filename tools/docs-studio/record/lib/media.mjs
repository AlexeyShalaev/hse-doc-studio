// Кадр шага: PNG из Playwright → WebP 1600 px (сайт и панель показывают его не шире), качество 80.
import sharp from 'sharp'
import {mkdir} from 'node:fs/promises'
import {dirname} from 'node:path'

export const SHOT_WIDTH = 1600

export async function saveShot(png, file) {
  await mkdir(dirname(file), {recursive: true})
  await sharp(png).resize({width: SHOT_WIDTH, withoutEnlargement: true}).webp({quality: 80, effort: 5}).toFile(file)
}
