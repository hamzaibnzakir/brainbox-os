const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('brainbox', {
  position: () => ipcRenderer.invoke('orb-position'),
  move: (x, y) => ipcRenderer.invoke('set-orb-position', x, y),
  toggleSize: () => ipcRenderer.invoke('toggle-size')
});
