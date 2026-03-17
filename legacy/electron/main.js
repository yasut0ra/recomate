const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const { APP_ROOT, buildUvicornArgs, resolvePythonCommand } = require('../../scripts/python-runtime.cjs');

let mainWindow;
let pythonProcess;
const DEV_SERVER_URL = process.env.RECOMATE_UI_URL || 'http://localhost:5173';

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
  const uvicornArgs = buildUvicornArgs();
  const args = pythonCommand === 'py' ? ['-3', ...uvicornArgs] : uvicornArgs;

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
