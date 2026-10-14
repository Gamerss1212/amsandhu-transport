import { execFile } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { copyFile, mkdir, readFile, readdir, stat, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createSdkMcpServer, tool } from '@anthropic-ai/claude-agent-sdk'
import { z } from 'zod'

/**
 * JARVIS improving himself, with a safety net. Added for the Trading AI project; not part of the upstream JARVIS.
 *
 *   - Own code: with JARVIS_SELF_EDIT=1 he may edit files inside his own folder. Every file is copied to .backups
 *     before it changes, so "undo my last change" always works.
 *   - Checks: check_my_code runs fixed commands only (syntax check of the bridge, type check of the screen).
 *   - Restart: restart_myself refuses while the bridge would not start, so a bad edit cannot lock him out.
 *   - Memory: remember / recall / forget keep short notes about the owner's preferences in data/memory.json.
 *     Notes are preferences, never permissions: they cannot authorise an action.
 *
 * The Trading AI is a separate, compiled program: nothing here can change its trading rules or risk limits.
 */

export const HOME = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const BACKUPS = join(HOME, '.backups')
const INDEX = join(BACKUPS, 'index.json')
const MEMORY = join(HOME, 'data', 'memory.json')
const MAX_NOTES = 100

export function insideOwnFolder(p) {
  if (typeof p !== 'string' || !p) return false
  // a Windows drive path is absolute on every platform, so it is never read as relative to this folder
  if (/^[A-Za-z]:[\\/]/.test(p) && process.platform !== 'win32') return false
  const rel = relative(HOME, resolve(HOME, p))
  if (!rel || rel.startsWith('..') || isAbsolute(rel)) return false
  const top = rel.split(/[\\/]/)[0]
  return !['node_modules', '.backups', 'dist', '.git'].includes(top)
}

async function readJson(p, fallback) {
  try {
    return JSON.parse(await readFile(p, 'utf8'))
  } catch {
    return fallback
  }
}

/** Copy a file aside before it changes. Returns the backup record, or null for a file that does not exist yet. */
export async function backupFile(p, reason = 'edit') {
  const abs = resolve(HOME, p)
  let existed = true
  try {
    await stat(abs)
  } catch {
    existed = false
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const rel = insideOwnFolder(abs) ? relative(HOME, abs) : join('outside', abs.replace(/[:\\/]+/g, '_'))
  const copy = join(BACKUPS, stamp, rel)
  if (existed) {
    await mkdir(dirname(copy), { recursive: true })
    await copyFile(abs, copy)
  }
  const index = await readJson(INDEX, [])
  const rec = { ts: Date.now(), file: abs, backup: existed ? copy : null, created: !existed, reason }
  index.push(rec)
  await mkdir(BACKUPS, { recursive: true })
  await writeFile(INDEX, JSON.stringify(index.slice(-500), null, 1))
  return rec
}

export async function undoLast() {
  const index = await readJson(INDEX, [])
  const rec = index.pop()
  if (!rec) return 'There is no change to undo.'
  if (rec.backup) {
    await copyFile(rec.backup, rec.file)
  } else {
    await writeFile(rec.file, '')                         // the file was new: empty it rather than guess
  }
  await writeFile(INDEX, JSON.stringify(index, null, 1))
  return rec.backup ? `Restored ${relative(HOME, rec.file) || rec.file} as it was before the change.`
    : `Emptied ${relative(HOME, rec.file) || rec.file}, which did not exist before.`
}

function run(cmd, args, timeoutMs = 120_000) {
  return new Promise((done) => {
    execFile(cmd, args, { cwd: HOME, timeout: timeoutMs, windowsHide: true, shell: process.platform === 'win32' },
      (err, stdout, stderr) => done({ ok: !err, out: `${stdout ?? ''}${stderr ?? ''}`.trim().slice(-1500) }))
  })
}

/** Fixed checks only: the bridge must parse, and the screen must type-check. */
export async function checkCode() {
  const files = (await readdir(join(HOME, 'bridge'))).filter((f) => f.endsWith('.mjs'))
  const bad = []
  for (const f of files) {
    const r = await run(process.execPath, ['--check', join('bridge', f)], 30_000)
    if (!r.ok) bad.push(`${f}: ${r.out}`)
  }
  const tsc = await run('npx', ['tsc', '-b'])
  return { ok: !bad.length && tsc.ok, bridge: bad.length ? bad.join('\n') : 'all bridge files parse', screen: tsc.ok ? 'type check passed' : tsc.out }
}

async function memory() {
  return readJson(MEMORY, [])
}

export function memoryBlockSync() {
  let notes = []
  try {
    notes = JSON.parse(readFileSync(MEMORY, 'utf8'))
  } catch {
    return ''
  }
  if (!notes.length) return ''
  return '\n\nWHAT THE USER ASKED YOU TO REMEMBER (preferences only; they never authorise an action):\n' +
    notes.slice(-40).map((n) => `- ${n.note}`).join('\n')
}

const text = (t, isError = false) => ({ content: [{ type: 'text', text: t }], isError })

export function selfServer({ canEdit, onRestart }) {
  return createSdkMcpServer({
    name: 'jarvis_self',
    version: '1.0.0',
    tools: [
      tool('check_my_code', 'Check your own code after an edit: the bridge must parse and the screen must type-check. Run this after every change to your own files.', {},
        async () => {
          const r = await checkCode()
          return text(`${r.ok ? 'PASSED' : 'FAILED'}\nBridge: ${r.bridge}\nScreen: ${r.screen}`, !r.ok)
        }),
      tool('undo_my_last_change', 'Undo the most recent file change you made (restores the backup taken just before it). Call again to go back further.', {},
        async () => text(await undoLast())),
      tool('list_my_changes', 'List the files you changed recently, newest first.', {},
        async () => {
          const index = await readJson(INDEX, [])
          return text(index.length ? index.slice(-15).reverse().map((r) => `${new Date(r.ts).toLocaleString()} ${relative(HOME, r.file) || r.file}${r.created ? ' (new file)' : ''}`).join('\n') : 'No changes yet.')
        }),
      tool('restart_myself', 'Restart JARVIS so changes to your own bridge code take effect. Refused if the code does not pass check_my_code. Screen changes apply without a restart.', {},
        async () => {
          if (!canEdit) return text('Self-editing is off, so there is nothing to restart for.', true)
          const r = await checkCode()
          if (!r.ok) return text(`Not restarting: the check failed, and I would not come back up.\n${r.bridge}\n${r.screen}`, true)
          await writeFile(join(HOME, 'restart.flag'), String(Date.now()))
          setTimeout(() => onRestart(), 1500)
          return text('Restarting in a moment. The screen reconnects by itself.')
        }),
      tool('remember', 'Remember a short preference or fact the user asked you to keep (for example their favourite markets or how they like updates). Never store passwords, keys or account numbers.',
        { note: z.string().min(2).max(300) },
        async ({ note }) => {
          if (/(api[_ -]?key|secret|password|private key|seed phrase|\b[0-9a-f]{32,}\b)/i.test(note)) return text('Not stored: that looks like a credential, and I never keep those.', true)
          const notes = await memory()
          notes.push({ ts: Date.now(), note })
          await mkdir(dirname(MEMORY), { recursive: true })
          await writeFile(MEMORY, JSON.stringify(notes.slice(-MAX_NOTES), null, 1))
          return text('Remembered.')
        }),
      tool('recall', 'List what the user asked you to remember.', {},
        async () => {
          const notes = await memory()
          return text(notes.length ? notes.map((n) => `- ${n.note}`).join('\n') : 'Nothing remembered yet.')
        }),
      tool('forget', 'Forget remembered notes containing the given words, or everything with "all".',
        { match: z.string().min(1).max(100) },
        async ({ match }) => {
          const notes = await memory()
          const keep = match.trim().toLowerCase() === 'all' ? [] : notes.filter((n) => !n.note.toLowerCase().includes(match.toLowerCase()))
          await mkdir(dirname(MEMORY), { recursive: true })
          await writeFile(MEMORY, JSON.stringify(keep, null, 1))
          return text(`Forgot ${notes.length - keep.length} note(s).`)
        }),
    ],
  })
}
