const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("rasentinelDesktop", {
  isDesktop: true,
  getStatus: () => ipcRenderer.invoke("rasentinel:get-desktop-status"),
  openLogs: () => ipcRenderer.invoke("rasentinel:open-logs"),
  openDataFolder: () => ipcRenderer.invoke("rasentinel:open-data")
});
