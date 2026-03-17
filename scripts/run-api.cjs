const { spawn } = require('child_process');

const { APP_ROOT, buildUvicornArgs, resolvePythonCommand } = require('./python-runtime.cjs');

const pythonCommand = resolvePythonCommand();
const extraArgs = process.argv.slice(2);
const uvicornArgs = buildUvicornArgs(extraArgs);
const args = pythonCommand === 'py' ? ['-3', ...uvicornArgs] : uvicornArgs;

const child = spawn(pythonCommand, args, {
  cwd: APP_ROOT,
  stdio: 'inherit',
});

child.on('error', (error) => {
  console.error(`Failed to start API server with "${pythonCommand}": ${error.message}`);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
