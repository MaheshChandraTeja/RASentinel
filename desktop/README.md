# RASentinel Desktop

Electron desktop shell for RASentinel.

This shell starts the local FastAPI backend, serves the built React frontend from a local desktop-only HTTP server, and opens the product inside an Electron window instead of a browser tab.

## Development desktop mode

From the project root:

```powershell
.\scripts\run_desktop_dev.ps1
```

This starts Vite and Electron together. The backend is started by Electron.

## Local desktop mode without browser

From the project root:

```powershell
.\scripts\run_desktop.ps1
```

This builds the frontend, starts the local backend, serves the built UI at `127.0.0.1:43175`, and opens Electron.

## Manual commands

```powershell
cd F:\Projects-INT\RASentinel\desktop
pnpm install
pnpm start
```

## Packaging preview

```powershell
cd F:\Projects-INT\RASentinel\desktop
pnpm package:win
```

The packaged build copies the backend source and frontend build into Electron resources. It still expects Python to be available on the target machine unless you later package the backend as a standalone executable with PyInstaller. That should be a separate packaging module, not a surprise hidden inside the UI shell like a clown in a server rack.

## Runtime data

The desktop shell stores local runtime files under Electron's user-data folder:

- `rasentinel.db`
- desktop logs
- backend logs

Open them from the RASentinel menu:

- `Open Diagnostics Logs`
- `Open Local Data Folder`
