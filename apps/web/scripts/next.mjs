import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const rootEnvironment = fileURLToPath(new URL("../../../.env", import.meta.url));
if (existsSync(rootEnvironment)) process.loadEnvFile(rootEnvironment);

// Disable framework telemetry before Next loads, for every supported npm command.
const require = createRequire(import.meta.url);
const child = spawn(process.execPath, [require.resolve("next/dist/bin/next"), ...process.argv.slice(2)], {
  stdio: "inherit",
  env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
});
child.on("error", (error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
child.on("exit", (code) => { process.exitCode = code ?? 1; });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
