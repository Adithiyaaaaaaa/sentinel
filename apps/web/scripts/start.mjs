import { cpSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const standalone = resolve(webRoot, ".next/standalone/apps/web");
const entry = resolve(standalone, "server.js");
if (!existsSync(entry)) {
  process.stderr.write("Production build missing. Run npm run build first.\n");
  process.exit(1);
}
// Standalone output intentionally excludes static assets; serve them locally.
cpSync(resolve(webRoot, ".next/static"), resolve(standalone, ".next/static"), { recursive: true });
if (existsSync(resolve(webRoot, "public"))) {
  cpSync(resolve(webRoot, "public"), resolve(standalone, "public"), { recursive: true });
}
const child = spawn(process.execPath, [entry], {
  stdio: "inherit",
  env: { ...process.env, NODE_ENV: "production", HOSTNAME: "127.0.0.1", PORT: process.env.PORT ?? "3000", NEXT_TELEMETRY_DISABLED: "1" },
});
child.on("error", (error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
child.on("exit", (code) => { process.exitCode = code ?? 1; });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
