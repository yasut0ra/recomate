const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess;

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
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

// Pythonサーバーを起動
function startPythonServer() {
  const pythonPath = path.join(__dirname, '../venv/Scripts/python');
  const scriptPath = path.join(__dirname, '../api/main.py');
  
  pythonProcess = spawn(pythonPath, [scriptPath]);

  pythonProcess.stdout.on('data', (data) => {
    console.log(`Python Server: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python Server Error: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python Server exited with code ${code}`);
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