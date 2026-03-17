const { spawn } = require('child_process');

const { APP_ROOT, resolvePythonCommand } = require('./python-runtime.cjs');

const python = resolvePythonCommand();
const args = ['-m', 'pytest', ...process.argv.slice(2)];

const child = spawn(python, args, {
  cwd: APP_ROOT,
  env: process.env,
  stdio: 'inherit',
});

child.on('exit', code => {
  process.exit(code ?? 1);
});

child.on('error', error => {
  console.error(`[recomate] Failed to start pytest with "${python}": ${error.message}`);
  process.exit(1);
});
