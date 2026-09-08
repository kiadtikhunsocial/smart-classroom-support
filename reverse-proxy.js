// Reverse proxy: one public ngrok domain serves BOTH backend API and n8n (LINE).
//   /api/*, /docs, /openapi.json, /health, /healthz  -> backend  :8000
//   everything else                                    -> n8n      :5678  (LINE webhook etc)
// Run: node reverse-proxy.js   (listens on PORT, default 9090)
const http = require("http");

const BACKEND = { host: "127.0.0.1", port: 8000 };
const N8N = { host: "127.0.0.1", port: 5678 };
const PORT = process.env.PROXY_PORT || 9090;

function isBackendPath(p) {
  return (
    p === "/health" || p === "/healthz" ||
    p.startsWith("/api/") || p === "/api" ||
    p === "/docs" || p.startsWith("/docs") ||
    p === "/openapi.json" || p === "/redoc"
  );
}

function forward(req, res, target) {
  const proxy = http.request(
    {
      host: target.host,
      port: target.port,
      path: req.url,
      method: req.method,
      headers: { ...req.headers, host: `${target.host}:${target.port}` },
    },
    (up) => {
      res.writeHead(up.statusCode, up.headers);
      up.pipe(res);
    }
  );
  proxy.on("error", (e) => {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "proxy upstream error", detail: String(e && e.message) }));
  });
  req.pipe(proxy);
}

http
  .createServer((req, res) => {
    const target = isBackendPath(req.url || "/") ? BACKEND : N8N;
    forward(req, res, target);
  })
  .listen(PORT, () => {
    console.log(`reverse-proxy listening on :${PORT}  backend=:${BACKEND.port} n8n=:${N8N.port}`);
  });
