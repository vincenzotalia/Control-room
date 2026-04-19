$ErrorActionPreference = "Stop"

# Demo deployment script for:
# - Backend: Azure App Service Linux
# - Frontend: Azure Static Web Apps
#
# Replace only these two values before running:
# - $GitHubRepoUrl
# - $GitHubBranch

$ProjectSlug = "control-room"
$Location = "westeurope"
$ResourceGroup = "rg-$ProjectSlug-demo-we"

$BackendPlan = "plan-$ProjectSlug-demo-we"
$BackendApp = "$ProjectSlug-demo-api"
$FrontendApp = "$ProjectSlug-demo-web"

$PythonRuntime = "PYTHON|3.11"
$PlanSku = "B1"
$FrontendSku = "Free"

$GitHubRepoUrl = "https://github.com/<owner>/<repo>"
$GitHubBranch = "main"

Write-Host "Creating resource group $ResourceGroup in $Location..."
az group create `
  --name $ResourceGroup `
  --location $Location

Write-Host "Creating Linux App Service plan $BackendPlan..."
az appservice plan create `
  --resource-group $ResourceGroup `
  --name $BackendPlan `
  --is-linux `
  --sku $PlanSku `
  --location $Location

Write-Host "Creating backend web app $BackendApp..."
az webapp create `
  --resource-group $ResourceGroup `
  --plan $BackendPlan `
  --name $BackendApp `
  --runtime $PythonRuntime `
  --startup-file "startup.txt"

Write-Host "Configuring backend app settings..."
az webapp config appsettings set `
  --resource-group $ResourceGroup `
  --name $BackendApp `
  --settings `
    WCR_ENV=production `
    WCR_HOST=0.0.0.0 `
    WCR_PORT=8000 `
    WCR_RELOAD=false `
    WCR_CORS_ORIGINS="https://$FrontendApp.azurestaticapps.net" `
    WCR_STORAGE_ROOT=/home/site/wwwroot/runtime `
    WCR_UPLOAD_ROOT=/home/site/wwwroot/runtime/uploads/area_manager `
    WCR_CACHE_ROOT=/home/site/wwwroot/runtime/.runtime-cache `
    WCR_DATA_ROOT=/home/site/wwwroot/runtime/data `
    WCR_DATA_INPUT_DIR=/home/site/wwwroot/runtime/data/input `
    WCR_DATA_HISTORY_DIR=/home/site/wwwroot/runtime/data/history `
    WCR_ALERT_HUB_DB_PATH=/home/site/wwwroot/runtime/alert_hub.db `
    WCR_AREA_MANAGER_DB_PATH=/home/site/wwwroot/runtime/area_manager.db `
    WCR_ALERT_HUB_PIN=change-me-demo-pin `
    WCR_AREA_MANAGER_PIN=change-me-demo-pin `
    WCR_FILE_STORAGE_BACKEND=local `
    SCM_DO_BUILD_DURING_DEPLOYMENT=true

Write-Host "Enforcing backend runtime and always-on demo settings..."
az webapp config set `
  --resource-group $ResourceGroup `
  --name $BackendApp `
  --linux-fx-version $PythonRuntime `
  --always-on false `
  --http20-enabled true `
  --min-tls-version 1.2

Write-Host "Creating frontend Static Web App $FrontendApp..."
az staticwebapp create `
  --resource-group $ResourceGroup `
  --name $FrontendApp `
  --location $Location `
  --sku $FrontendSku `
  --source $GitHubRepoUrl `
  --branch $GitHubBranch `
  --app-location "frontend" `
  --output-location "dist" `
  --login-with-github

Write-Host "Configuring frontend build-time environment variable..."
az staticwebapp appsettings set `
  --resource-group $ResourceGroup `
  --name $FrontendApp `
  --setting-names `
    VITE_API_BASE_URL="https://$BackendApp.azurewebsites.net"

Write-Host ""
Write-Host "Demo resources created."
Write-Host "Backend URL : https://$BackendApp.azurewebsites.net"
Write-Host "Frontend URL: https://$FrontendApp.azurestaticapps.net"
Write-Host ""
Write-Host "Next manual steps:"
Write-Host "1. Deploy the backend code from the backend/ folder to $BackendApp."
Write-Host "2. Confirm GET / on the backend."
Write-Host "3. Let Static Web Apps complete the GitHub build for the frontend."
Write-Host "4. Upload only demo data."
