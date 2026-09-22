const { app, BrowserWindow, ipcMain, screen, Tray, Menu } = require('electron');
const path = require('path');

let win;
let tray;

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
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false }
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
});

ipcMain.handle('orb-position', () => win.getPosition());
ipcMain.handle('set-orb-position', (_, x, y) => win.setPosition(Math.round(x), Math.round(y), false));
ipcMain.handle('toggle-size', () => {
  const [w, h] = win.getSize();
  const next = w < 140 ? 360 : 96;
  win.setSize(next, next === 96 ? next : 520, true);
});

app.on('window-all-closed', e => e.preventDefault());
