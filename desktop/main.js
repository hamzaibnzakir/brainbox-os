const { app, BrowserWindow, ipcMain, Tray, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let win;
let tray;
let brainboxProcess;

function pythonPath() {
  return process.platform === 'win32'
    ? path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe')
    : path.join(__dirname, '..', '.venv', 'bin', 'python');
}

function startBrainboxRuntime() {
  const executable = pythonPath();
  brainboxProcess = spawn(executable, ['-m', 'brainbox_os.cli', '--dev'], {
    cwd: path.join(__dirname, '..'),
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  });

  let buffer = '';
  brainboxProcess.stdout.on('data', chunk => {
    buffer += chunk.toString();
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || '';
    for (const line of lines) {
      try {
        const event = JSON.parse(line);
        if (win && !win.isDestroyed()) win.webContents.send('brainbox-event', event);
      } catch (_) {}
    }
  });

  brainboxProcess.stderr.on('data', chunk => {
    if (win && !win.isDestroyed()) {
      win.webContents.send('brainbox-event', { event: 'log', text: chunk.toString() });
    }
  });

  brainboxProcess.on('error', error => {
    if (win && !win.isDestroyed()) {
      win.webContents.send('brainbox-event', { event: 'error', error: error.message });
    }
  });
}

function stopBrainboxRuntime() {
  if (brainboxProcess && !brainboxProcess.killed) {
    brainboxProcess.kill();
  }
  brainboxProcess = null;
}

function createWindow() {
  win = new BrowserWindow({
    width: 96,
    height: 96,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.setAlwaysOnTop(true, 'floating');
  win.loadFile(path.join(__dirname, 'index.html'));
  win.setIgnoreMouseEvents(false);
}

app.whenReady().then(() => {
  createWindow();
  tray = new Tray(path.join(__dirname, 'orb.png'));
  tray.setToolTip('Brainbox OS');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show Brainbox', click: () => win.show() },
    { label: 'Quit', click: () => app.quit() }
  ]));
  startBrainboxRuntime();
});

ipcMain.handle('orb-position', () => win.getPosition());
ipcMain.handle('set-orb-position', (_, x, y) => win.setPosition(Math.round(x), Math.round(y), false));
ipcMain.handle('toggle-size', () => {
  const [w] = win.getSize();
  const next = w < 140 ? 360 : 96;
  win.setSize(next, next === 96 ? next : 520, true);
});

app.on('before-quit', () => stopBrainboxRuntime());
app.on('window-all-closed', e => e.preventDefault());
