# Azure Demo Deploy

This repository is now prepared for a fast demo deployment with two separate Azure services:

- Frontend: Azure Static Web Apps
- Backend: Azure App Service Linux

This is intentionally a demo setup:

- single instance
- local SQLite persistence
- local runtime file storage under App Service persistent path
- no production authentication hardening

## Recommended layout

Deploy the two folders separately:

- Frontend source: `frontend/`
- Backend source: `backend/`

## Frontend demo deploy

Target service:

- Azure Static Web Apps

Folder settings:

- App location: `frontend`
- Output location: `dist`

Environment file:

- Start from [frontend/.env.azure-demo.example](frontend/.env.azure-demo.example)
- Set `VITE_API_BASE_URL` to the final backend URL

Routing:

- SPA fallback is already configured in [frontend/public/staticwebapp.config.json](frontend/public/staticwebapp.config.json)

Build command:

```bash
npm install
npm run build
```

## Backend demo deploy

Target service:

- Azure App Service Linux, Python stack

Source folder:

- `backend/`

Startup command:

- `startup.txt`

You can also set the startup command directly to:

```text
python server.py
```

Environment file:

- Start from [backend/.env.azure-demo.example](backend/.env.azure-demo.example)

Important app settings for demo:

```text
WCR_ENV=production
WCR_RELOAD=false
WCR_CORS_ORIGINS=https://<your-frontend-domain>
WCR_STORAGE_ROOT=/home/site/wwwroot/runtime
WCR_DATA_ROOT=/home/site/wwwroot/runtime/data
WCR_ALERT_HUB_DB_PATH=/home/site/wwwroot/runtime/alert_hub.db
WCR_AREA_MANAGER_DB_PATH=/home/site/wwwroot/runtime/area_manager.db
WCR_ALERT_HUB_PIN=<demo-pin>
WCR_AREA_MANAGER_PIN=<demo-pin>
WCR_FILE_STORAGE_BACKEND=local
```

For a custom container demo on App Service Linux, persistent writes should stay under `/home`; Microsoft documents `/home` as the persistent path when App Service storage is enabled for Linux custom containers.

## Demo checklist

1. Publish backend first and confirm `GET /` responds.
2. Set the frontend `VITE_API_BASE_URL` to the backend URL.
3. Publish frontend.
4. Upload only demo files and demo PDFs.
5. Keep the App Service at one instance.
6. Do not present this environment as production-ready.

## Azure CLI shortcut

If you want a faster setup with your chosen values already filled in:

- project: `Control room`
- region: `West Europe`
- domain: Azure default URLs only

Use:

- [deploy_azure_demo.ps1](deploy_azure_demo.ps1)
- [AZURE_DEMO_CLI.md](AZURE_DEMO_CLI.md)

## Later upgrade path

When the demo is approved, the next upgrade should be:

1. move SQLite to a managed database
2. move file persistence to Azure Blob Storage
3. add real authentication
4. add CI/CD and environment separation
