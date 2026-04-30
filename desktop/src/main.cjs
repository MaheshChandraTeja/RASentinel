const { app, BrowserWindow, dialog, Menu, shell } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");
const { spawn } = require("node:child_process");

const BACKEND_HOST = process.env.RASENTINEL_BACKEND_HOST || "127.0.0.1";
const BACKEND_PORT = Number(process.env.RASENTINEL_BACKEND_PORT || "8000");
const BACKEND_BASE_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`;
const API_BASE_URL = `${BACKEND_BASE_URL}/api/v1`;

let mainWindow = null;
let backendProcess = null;
let backendStartedByElectron = false;

const devProjectRoot = path.resolve(__dirname, "..", "..");

app.setName("RASentinel");
app.setAppUserModelId("com.kairais.rasentinel");

function toPosix(value) {
  return value.replace(/\\/g, "/");
}

function exists(filePath) {
  try {
    return fs.existsSync(filePath);
  } catch {
    return false;
  }
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function getRuntimeRoot() {
  if (app.isPackaged) {
    return process.resourcesPath;
  }

  return devProjectRoot;
}

function resolveAppIconPath() {
  const runtimeRoot = getRuntimeRoot();

  const packagedIcon = path.join(runtimeRoot, "assets", "rasentinel.ico");
  if (app.isPackaged && exists(packagedIcon)) {
    return packagedIcon;
  }

  const devIcon = path.join(devProjectRoot, "desktop", "assets", "rasentinel.ico");
  if (exists(devIcon)) {
    return devIcon;
  }

  return path.join(devProjectRoot, "desktop", "assets", "rasentinel.png");
}

function requestJson(url, timeoutMs = 1200) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: timeoutMs }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        body += chunk;
      });
      response.on("end", () => {
        if (response.statusCode && response.statusCode >= 200 && response.statusCode < 300) {
          resolve(body);
        } else {
          reject(new Error(`HTTP ${response.statusCode}: ${body}`));
        }
      });
    });

    request.on("timeout", () => {
      request.destroy(new Error("Request timed out"));
    });

    request.on("error", reject);
  });
}

async function isBackendHealthy() {
  try {
    await requestJson(`${API_BASE_URL}/health`, 800);
    return true;
  } catch {
    return false;
  }
}

async function waitForBackend(timeoutMs = 45000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isBackendHealthy()) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

function createBackendEnvironment() {
  const userDataDir = app.getPath("userData");
  const dataDir = path.join(userDataDir, "data");
  const logsDir = path.join(dataDir, "logs");
  const reportsDir = path.join(dataDir, "reports");
  const databasePath = path.join(dataDir, "rasentinel.db");

  ensureDir(dataDir);
  ensureDir(logsDir);
  ensureDir(reportsDir);

  return {
    ...process.env,
    RASENTINEL_APP_NAME: "RASentinel",
    RASENTINEL_ENV: "desktop",
    RASENTINEL_API_PREFIX: "/api/v1",
    RASENTINEL_DATABASE_URL: `sqlite:///${toPosix(databasePath)}`,
    RASENTINEL_DATA_DIR: dataDir,
    RASENTINEL_LOG_DIR: logsDir,
    RASENTINEL_REPORTS_DIR: reportsDir,
    RASENTINEL_DESKTOP_USER_DATA: userDataDir,
    RASENTINEL_CORS_ORIGINS: "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8000,file://",
    RASENTINEL_HOST: BACKEND_HOST,
    RASENTINEL_PORT: String(BACKEND_PORT),
    PYTHONUNBUFFERED: "1",
  };
}

function resolveDevPythonExecutable() {
  const envPython = process.env.RASENTINEL_PYTHON_PATH || process.env.PYTHON;
  const candidates = [];

  if (envPython) {
    candidates.push(envPython);
  }

  if (process.platform === "win32") {
    candidates.push(path.join(devProjectRoot, "backend", ".venv", "Scripts", "python.exe"));
    candidates.push(path.join(devProjectRoot, ".venv", "Scripts", "python.exe"));
  } else {
    candidates.push(path.join(devProjectRoot, "backend", ".venv", "bin", "python"));
    candidates.push(path.join(devProjectRoot, ".venv", "bin", "python"));
  }

  for (const candidate of candidates) {
    if (candidate && exists(candidate)) {
      return {
        command: candidate,
        argsPrefix: [],
        display: candidate,
      };
    }
  }

  if (process.platform === "win32") {
    return {
      command: "py",
      argsPrefix: ["-3"],
      display: "py -3",
    };
  }

  return {
    command: "python3",
    argsPrefix: [],
    display: "python3",
  };
}

function resolveBackendCommand() {
  if (app.isPackaged) {
    const backendExe = path.join(process.resourcesPath, "backend", "rasentinel-backend.exe");

    if (!exists(backendExe)) {
      throw new Error(
        `Packaged backend executable was not found.\n\nExpected:\n${backendExe}\n\nRebuild with scripts/package_windows.ps1.`
      );
    }

    return {
      command: backendExe,
      args: [],
      cwd: path.dirname(backendExe),
      display: backendExe,
    };
  }

  const backendDir = path.join(devProjectRoot, "backend");
  const backendEntry = path.join(backendDir, "app", "main.py");

  if (!exists(backendEntry)) {
    throw new Error(
      `Backend entrypoint was not found.\n\nExpected:\n${backendEntry}\n\nRun Electron from the RASentinel project root or restore the backend folder.`
    );
  }

  const python = resolveDevPythonExecutable();

  return {
    command: python.command,
    args: [
      ...python.argsPrefix,
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      BACKEND_HOST,
      "--port",
      String(BACKEND_PORT),
    ],
    cwd: backendDir,
    display: python.display,
    pythonDisplay: python.display,
  };
}

function startBackend() {
  const backend = resolveBackendCommand();
  const env = createBackendEnvironment();

  if (!app.isPackaged) {
    env.PYTHONPATH = path.join(devProjectRoot, "backend");
  }

  backendProcess = spawn(backend.command, backend.args, {
    cwd: backend.cwd,
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  backendStartedByElectron = true;

  backendProcess.stdout.on("data", (data) => {
    console.log(`[RASentinel backend] ${data.toString().trimEnd()}`);
  });

  backendProcess.stderr.on("data", (data) => {
    console.error(`[RASentinel backend] ${data.toString().trimEnd()}`);
  });

  backendProcess.on("error", (error) => {
    dialog.showErrorBox(
      "RASentinel backend failed to start",
      `Could not start the bundled diagnostics backend.\n\nResolved command:\n${backend.display}\n\nError:\n${error.message}`
    );
  });

  backendProcess.on("exit", (code, signal) => {
    if (code !== 0 && code !== null) {
      console.error(`[RASentinel backend] exited with code ${code}`);
    }
    if (signal) {
      console.error(`[RASentinel backend] exited with signal ${signal}`);
    }
  });
}

async function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    title: "RASentinel",
    icon: resolveAppIconPath(),
    backgroundColor: "#070a12",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (process.env.RASENTINEL_DESKTOP_DEV === "1") {
    await mainWindow.loadURL("http://127.0.0.1:5173");
    return;
  }

  const indexHtml = app.isPackaged
    ? path.join(process.resourcesPath, "frontend", "dist", "index.html")
    : path.join(devProjectRoot, "frontend", "dist", "index.html");

  if (!exists(indexHtml)) {
    throw new Error(
      `Built frontend was not found.\n\nExpected:\n${indexHtml}\n\nRun:\ncd frontend\npnpm build`
    );
  }

  await mainWindow.loadFile(indexHtml);
}

async function boot() {
  Menu.setApplicationMenu(null);

  if (!(await isBackendHealthy())) {
    startBackend();
    const ready = await waitForBackend(45000);
    if (!ready) {
      throw new Error(
        `Backend did not become healthy within 45 seconds.\n\nCheck whether port ${BACKEND_PORT} is already in use, or run the backend executable manually to inspect its logs.`
      );
    }
  }

  await createMainWindow();
}

app.whenReady().then(() => {
  boot().catch((error) => {
    dialog.showErrorBox("RASentinel startup error", error.stack || error.message || String(error));
    app.quit();
  });
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow().catch((error) => {
      dialog.showErrorBox("RASentinel window error", error.stack || error.message || String(error));
    });
  }
});

app.on("before-quit", () => {
  if (backendProcess && backendStartedByElectron && !backendProcess.killed) {
    backendProcess.kill();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
