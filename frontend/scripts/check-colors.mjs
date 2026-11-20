import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../src/', import.meta.url))
const rawColor = /#[\da-f]{3,8}\b|\b(?:rgba?|hsla?)\s*\(/i
const namedColor = /(?:^|[;{])\s*(?:color|background(?:-color)?|border(?:-[a-z]+)?-color|outline-color|text-decoration-color|fill|stroke)\s*:\s*(?:white|black|red|green|blue|gray|grey|yellow|orange|purple)\b/i
const violations = []

async function scan(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) await scan(path)
    else if (/\.(?:css|vue|ts)$/.test(entry.name) && entry.name !== 'tokens.css') {
      const contents = await readFile(path, 'utf8')
      if (rawColor.test(contents) || namedColor.test(contents)) violations.push(relative(root, path))
    }
  }
}

await scan(root)
if (violations.length) {
  console.error(`Use frontend/src/styles/tokens.css for colors:\n${violations.join('\n')}`)
  process.exitCode = 1
}
