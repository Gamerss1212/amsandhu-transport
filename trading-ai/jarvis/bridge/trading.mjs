import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createSdkMcpServer, tool } from '@anthropic-ai/claude-agent-sdk'
import { z } from 'zod'

/**
 * A READ-ONLY window onto the Trading AI running on this computer.
 *
 * Added for the Trading AI project; not part of the upstream JARVIS.
 *
 * What it can do: fetch a short list of information pages (status, risk, account, agents, activity, temperature,
 * learning) from the Trading AI's local server and hand the text to the model.
 *
 * What it cannot do, by construction rather than by instruction:
 *   - it only ever sends GET requests, to paths in ALLOWED below;
 *   - it holds only the Trading AI's READ-ONLY token (X-TA-Read-Token), which the server itself refuses on every
 *     other route, on every non-GET method, and on connections, brokers, credentials and the audit chain;
 *   - it has no tool that places, cancels or changes anything, arms live trading, changes a limit or stops the system.
 *
 * Text returned here is DATA. Web pages and search results the model reads elsewhere are data too; neither can
 * instruct this server to do anything, because there is nothing here that acts.
 */

const HERE = dirname(fileURLToPath(import.meta.url))

/** Where the Trading AI writes its link file at every start: <Trading AI folder>/data/jarvis-link.json. */
export const LINK_FILE =
  process.env.JARVIS_TRADING_LINK ?? resolve(HERE, '..', '..', 'data', 'jarvis-link.json')

const MAX_CHARS = 9000
const TIMEOUT_MS = 12000

/** Mirrors the server's own read-only allowlist. The server enforces it again; this is the second lock. */
const ALLOWED = new Set([
  '/api/overview', '/api/fleet/summary', '/api/fleet', '/api/learning', '/api/market/strip', '/api/daytrade',
  '/api/activity', '/api/autopilot', '/api/system/thermal', '/api/account', '/api/risk', '/api/orders',
  '/api/fills', '/api/decisions', '/api/equity', '/api/report/session', '/api/report/attribution', '/api/events',
])
const AGENT_ID = /^A\d{3}$/

export function pathAllowed(path) {
  if (ALLOWED.has(path)) return true
  const m = /^\/api\/fleet\/(.+)$/.exec(path)
  return !!m && AGENT_ID.test(m[1])
}

async function readLink(linkFile) {
  let raw
  try {
    raw = await readFile(linkFile, 'utf8')
  } catch {
    throw new Error('the Trading AI is not running (no link file). Start START_TRADING_AI.exe first.')
  }
  const link = JSON.parse(raw)
  if (typeof link.url !== 'string' || typeof link.read_token !== 'string') throw new Error('the link file is damaged')
  const url = new URL(link.url)
  if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') throw new Error('the link points off this computer')
  return { origin: url.origin, token: link.read_token }
}

/** One GET. Returns { ok, text }. Never throws, so a tool failure is one plain sentence for the model. */
export async function readTrading(path, { linkFile = LINK_FILE, fetchImpl = fetch } = {}) {
  try {
    if (!pathAllowed(path)) return { ok: false, text: 'That page is not available to a read-only link.' }
    const { origin, token } = await readLink(linkFile)
    const res = await fetchImpl(origin + path, {
      method: 'GET',
      headers: { 'X-TA-Read-Token': token },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
    if (!res.ok) return { ok: false, text: `The Trading AI answered HTTP ${res.status}.` }
    let body = JSON.stringify(await res.json())
    if (body.length > MAX_CHARS) body = body.slice(0, MAX_CHARS) + ' …(cut: too long to read out)'
    return {
      ok: true,
      text:
        'DATA from the Trading AI on this computer (read-only; every figure below was computed by that program, ' +
        'not estimated):\n' + body,
    }
  } catch (e) {
    return { ok: false, text: `Could not read the Trading AI: ${e instanceof Error ? e.message : String(e)}` }
  }
}

const NONE = {}
export const TRADING_TOOLS = [
  ['get_trading_overview', '/api/overview', 'Overall state of the Trading AI: mode (paper or live), system state, counts.'],
  ['get_trading_agents', '/api/fleet/summary', 'The master agent and its 100 trading agents: how many have a market, a validated version, permission to trade.'],
  ['get_trading_risk', '/api/risk', 'Risk limits, the daily loss counter, drawdown, and whether the emergency stop is engaged.'],
  ['get_trading_account', '/api/account', 'The paper (or connected) account: balance, equity, open positions.'],
  ['get_trading_activity', '/api/activity', 'Recent decisions and actions of the agents.'],
  ['get_trading_learning', '/api/learning', 'Mistakes the agents recorded, the lessons learned and the safeguards in force.'],
  ['get_trading_temperature', '/api/system/thermal', 'This computer\'s CPU temperature and throttling, as Windows reports them, and the last thermal check.'],
  ['get_trading_report', '/api/report/session', 'The session report: results of the current run.'],
]

export function tradingServer() {
  const tools = TRADING_TOOLS.map(([name, path, description]) =>
    tool(name, description + ' Read-only. Report only what it returns.', NONE, async () => {
      const r = await readTrading(path)
      return { content: [{ type: 'text', text: r.text }], isError: !r.ok }
    }),
  )
  tools.push(
    tool(
      'get_trading_agent',
      'One trading agent by id (A001 to A100): its market, role, versions, permission and mistakes. Read-only.',
      { id: z.string().regex(AGENT_ID).describe('Agent id such as A004') },
      async ({ id }) => {
        const r = await readTrading(`/api/fleet/${id}`)
        return { content: [{ type: 'text', text: r.text }], isError: !r.ok }
      },
    ),
  )
  return createSdkMcpServer({ name: 'jarvis_trading', version: '1.0.0', tools })
}
