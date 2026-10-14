// Safety rules of the JARVIS bridge, checked on whatever computer runs them (Linux here, real Windows in CI).
// Added for the Trading AI project. Run: npm run test:bridge
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { existsSync } from 'node:fs'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { HOME, TRADING_ROOT, backupFile, insideOwnFolder, touchesTradingAI, undoLast } from './self.mjs'
import { openTradingWindow } from './trading.mjs'

const win = (p) => p.replace(/\//g, '\\')

test('his own folder is editable, everything around it is not', () => {
  assert.equal(insideOwnFolder(join(HOME, 'src', 'ui', 'Confirm.tsx')), true)
  assert.equal(insideOwnFolder(join(HOME, 'bridge', 'server.mjs')), true)
  assert.equal(insideOwnFolder(join(TRADING_ROOT, 'backend', 'tradingai', 'risk', 'service.py')), false)
  assert.equal(insideOwnFolder(join(HOME, 'node_modules', 'x.js')), false)
  assert.equal(insideOwnFolder(join(HOME, '.backups', 'x')), false)
  assert.equal(insideOwnFolder(join(HOME, '..', 'START_TRADING_AI.exe')), false)
})

test('nothing aimed at the Trading AI gets through, whatever the slashes', () => {
  const blocked = [
    ['Edit', { file_path: join(TRADING_ROOT, 'backend', 'tradingai', 'risk', 'service.py') }],
    ['Write', { file_path: join(TRADING_ROOT, 'data', 'settings.json') }],
    ['Write', { file_path: join(TRADING_ROOT, '_internal', 'tradingai', 'risk', 'service.py') }],
    ['Edit', { file_path: join(HOME, '..', 'START_TRADING_AI.exe') }],
    ['Bash', { command: `sqlite3 "${join(TRADING_ROOT, 'data', 'tradingai.sqlite')}" "update limits set x=1"` }],
    ['Bash', { command: `del ${win(join(TRADING_ROOT, 'data', 'jarvis-link.json'))}` }],
    ['PowerShell', { command: `Set-Content ${win(join(TRADING_ROOT, 'data', 'x.json'))} 1` }],
    ['Bash', { command: 'echo 1 > C:\\Users\\me\\Downloads\\TradingAI\\_internal\\tradingai\\risk\\service.py' }],
  ]
  for (const [tool, input] of blocked) assert.equal(touchesTradingAI(tool, input), true, `${tool} ${JSON.stringify(input)}`)
})

test('his own work and unrelated files are not mistaken for the Trading AI', () => {
  const allowed = [
    ['Edit', { file_path: join(HOME, 'src', 'ui', 'Confirm.tsx') }],
    ['Write', { file_path: join(tmpdir(), 'notes.txt') }],
    ['Bash', { command: `cd "${join(TRADING_ROOT, 'jarvis')}" && npm run build` }],
    ['Bash', { command: `cd ${win(join(TRADING_ROOT, 'jarvis'))} && npx tsc -b` }],
    ['Read', { file_path: join(TRADING_ROOT, 'backend', 'tradingai', 'risk', 'service.py') }],
  ]
  for (const [tool, input] of allowed) assert.equal(touchesTradingAI(tool, input), false, `${tool} ${JSON.stringify(input)}`)
})

test('a change to his own file can be undone exactly', async () => {
  const hadBackups = existsSync(join(HOME, '.backups'))
  const file = join(HOME, 'src', '__undo_test.txt')
  await writeFile(file, 'before\n')
  try {
    await backupFile(file, 'test')
    await writeFile(file, 'after\n')
    await undoLast()
    assert.equal(await readFile(file, 'utf8'), 'before\n')
  } finally {
    await rm(file, { force: true })
    if (!hadBackups) await rm(join(HOME, '.backups'), { recursive: true, force: true })
  }
})

test('"opened" is said only when a window really started', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'jarvis-link-'))
  const linkFile = join(dir, 'jarvis-link.json')
  await writeFile(linkFile, JSON.stringify({ url: 'http://127.0.0.1:8000', read_token: 'r' }))
  const opener = (event, arg) => () => {
    const child = new EventEmitter()
    child.unref = () => {}
    setTimeout(() => child.emit(event, arg), 5)
    return child
  }
  try {
    const failed = await openTradingWindow('trading', { linkFile, run: opener('error', Object.assign(new Error('x'), { code: 'ENOENT' })) })
    assert.equal(failed.ok, false)
    assert.match(failed.text, /Could not open/)
    const opened = await openTradingWindow('brokers', { linkFile, run: opener('spawn') })
    assert.equal(opened.ok, true)
    assert.match(opened.text, /\/broker/)
    await writeFile(linkFile, JSON.stringify({ url: 'http://example.com', read_token: 'r' }))
    assert.equal((await openTradingWindow('trading', { linkFile, run: opener('spawn') })).ok, false)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})
