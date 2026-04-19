# Backend Azure Deploy

## App Service / Container Apps

Startup command:

```bash
python server.py
```

Required app settings in production:

```text
WCR_ENV=production
WCR_ALERT_HUB_PIN=<strong-secret>
WCR_AREA_MANAGER_PIN=<strong-secret>
WCR_CORS_ORIGINS=https://<frontend-domain>
WCR_STORAGE_ROOT=/home/site/wwwroot/runtime
WCR_UPLOAD_ROOT=/home/site/wwwroot/runtime/uploads/area_manager
WCR_CACHE_ROOT=/home/site/wwwroot/runtime/.runtime-cache
WCR_ALERT_HUB_DB_PATH=/home/site/wwwroot/runtime/alert_hub.db
WCR_AREA_MANAGER_DB_PATH=/home/site/wwwroot/runtime/area_manager.db
```

Optional app settings:

```text
WCR_DATA_INPUT_DIR=/home/site/wwwroot/data/input
WCR_DATA_HISTORY_DIR=/home/site/wwwroot/data/history
WCR_RELOAD=false
WCR_FILE_STORAGE_BACKEND=local
```

Notes:

- `PORT` is read automatically if Azure provides it.
- If `WCR_ENV=production` and the PIN variables are missing, startup fails by design.
- SQLite remains local filesystem persistence for now; uploaded PDFs and dataset files can already move to Blob Storage with the option below.

## Azure Blob option

If you want uploaded PDFs and data files on Blob Storage instead of local disk:

```text
WCR_FILE_STORAGE_BACKEND=azure_blob
AZURE_STORAGE_CONNECTION_STRING=<storage-connection-string>
WCR_BLOB_CONTAINER=warehouse-control-room
```

The backend keeps a local runtime cache for analytics and downloads.
