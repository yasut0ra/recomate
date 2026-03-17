const fs = require('fs');
const path = require('path');

const APP_ROOT = path.resolve(__dirname, '..');

function resolvePythonCommand() {
  const override = process.env.RECOMATE_PYTHON_BIN || process.env.PYTHON_BIN || process.env.PYTHON_PATH;
  if (override) {
    return override;
  }

  const candidates = process.platform === 'win32'
    ? [
        path.join(APP_ROOT, 'venv', 'Scripts', 'python.exe'),
        path.join(APP_ROOT, '.venv', 'Scripts', 'python.exe'),
        'py',
        'python',
      ]
    : [
        path.join(APP_ROOT, 'venv', 'bin', 'python'),
        path.join(APP_ROOT, '.venv', 'bin', 'python'),
        'python3',
        'python',
      ];

  return candidates.find(candidate => !candidate.includes(path.sep) || fs.existsSync(candidate)) || candidates[candidates.length - 1];
}

function buildUvicornArgs(extraArgs = []) {
  const host = process.env.RECOMATE_API_HOST || '127.0.0.1';
  const port = process.env.RECOMATE_API_PORT || '8000';
  return ['-m', 'uvicorn', 'api.main:app', '--host', host, '--port', port, ...extraArgs];
}

module.exports = {
  APP_ROOT,
  buildUvicornArgs,
  resolvePythonCommand,
};
