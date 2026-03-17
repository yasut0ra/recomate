const { app, BrowserWindow } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess;
const APP_ROOT = path.join(__dirname, '..');
const DEV_SERVER_URL = process.env.RECOMATE_UI_URL || 'http://localhost:5173';
const API_HOST = process.env.RECOMATE_API_HOST || '127.0.0.1';
const API_PORT = process.env.RECOMATE_API_PORT || '8000';

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

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  // 開発環境ではViteの開発サーバーを使用
  if (!app.isPackaged) {
    mainWindow.loadURL(DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(APP_ROOT, 'ui/dist/index.html'));
  }
}

// Pythonサーバーを起動
function startPythonServer() {
  const pythonCommand = resolvePythonCommand();
  const args = pythonCommand === 'py'
    ? ['-3', '-m', 'uvicorn', 'api.main:app', '--host', API_HOST, '--port', API_PORT]
    : ['-m', 'uvicorn', 'api.main:app', '--host', API_HOST, '--port', API_PORT];

  pythonProcess = spawn(pythonCommand, args, {
    cwd: APP_ROOT,
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`Python Server: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python Server Error: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python Server exited with code ${code}`);
  });

  pythonProcess.on('error', (error) => {
    console.error(`Failed to start Python Server: ${error.message}`);
  });
}

app.whenReady().then(() => {
  startPythonServer();
  createWindow();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

// アプリケーション終了時にPythonプロセスも終了
app.on('will-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
}); 
