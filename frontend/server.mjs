#!/usr/bin/env node
// Production frontend service: Vue assets + same-origin proxy to the independent API.
import http from 'node:http'
import https from 'node:https'
import { createReadStream, existsSync } from 'node:fs'
import { stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist')
const backend = new URL(process.env.SENTINEL_API_URL || 'http://127.0.0.1:18087')
const host = process.env.SENTINEL_WEB_HOST || '127.0.0.1'
const port = Number(process.env.SENTINEL_WEB_PORT || 8080)
if (!['http:', 'https:'].includes(backend.protocol)) throw new Error('API URL must use HTTP or HTTPS')
if (!existsSync(path.join(root, 'index.html'))) throw new Error('Frontend build missing. Run npm ci && npm run build first.')
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.json': 'application/json' }
const hopHeaders = ['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade']
function json(res, status, value) { const body = JSON.stringify(value); res.writeHead(status, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(body) }); res.end(body) }
const server = http.createServer(async (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff')
  res.setHeader('X-Frame-Options', 'DENY')
  res.setHeader('Referrer-Policy', 'same-origin')
  const rawPath = (req.url || '/').split('?')[0]
  if (rawPath === '/healthz') return json(res, 200, { ok: true, service: 'vps-sentinel-frontend' })
  if (rawPath.startsWith('/api/') || rawPath.startsWith('/downloads/')) {
    const headers = { ...req.headers }
    for (const key of hopHeaders) delete headers[key]
    delete headers['x-forwarded-for']; delete headers['x-forwarded-host']; delete headers['x-forwarded-proto']
    const transport = backend.protocol === 'https:' ? https : http
    const upstream = transport.request({ protocol: backend.protocol, hostname: backend.hostname, port: backend.port, path: req.url, method: req.method, headers, timeout: 30000 }, response => {
      const outgoing = { ...response.headers }
      for (const key of hopHeaders) delete outgoing[key]
      res.writeHead(response.statusCode || 502, outgoing)
      response.pipe(res)
    })
    upstream.on('timeout', () => upstream.destroy(new Error('API timeout')))
    upstream.on('error', () => { if (!res.headersSent) json(res, 502, { error: '后端暂不可用，请检查 vps-sentinel-api 服务', code: 'backend_unavailable' }); else res.destroy() })
    req.on('aborted', () => upstream.destroy())
    req.pipe(upstream)
    return
  }
  if (!['GET', 'HEAD'].includes(req.method)) return json(res, 405, { error: 'Method not allowed' })
  try {
    const requested = decodeURIComponent(rawPath)
    if (requested.includes('\0') || requested.split('/').some(part => part === '..' || part.startsWith('.'))) return json(res, 404, { error: 'Not found' })
    let target = path.resolve(root, '.' + requested)
    if (!target.startsWith(root + path.sep) && target !== root) return json(res, 404, { error: 'Not found' })
    let info = await stat(target).catch(() => null)
    if (!info?.isFile()) {
      if (path.extname(requested)) return json(res, 404, { error: 'Not found' })
      target = path.join(root, 'index.html'); info = await stat(target)
    }
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
    res.setHeader('Content-Type', types[path.extname(target)] || 'application/octet-stream')
    res.setHeader('Content-Length', info.size)
    res.setHeader('Cache-Control', target.endsWith('index.html') ? 'no-cache' : 'public, max-age=86400')
    if (req.method === 'HEAD') return res.end()
    createReadStream(target).on('error', () => res.destroy()).pipe(res)
  } catch { if (!res.headersSent) json(res, 400, { error: 'Invalid request' }); else res.destroy() }
})
server.headersTimeout = 10000
server.requestTimeout = 30000
server.listen(port, host, () => console.log(`VPS Sentinel frontend: http://${host}:${port}`))
function shutdown() { server.close(() => process.exit(0)); setTimeout(() => process.exit(0), 5000).unref() }
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
