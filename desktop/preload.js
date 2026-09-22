const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('brainbox', {
  onEvent: (callback) => ipcRenderer.on('brainbox-event', (_, event) => callback(event)),
  minimize: () => ipcRenderer.send('window-minimize'),
  quit: () => ipcRenderer.send('quit-brainbox'),
  getPosition: () => ipcRenderer.invoke('window-position'),
  getState: () => ipcRenderer.invoke('runtime-state')
});