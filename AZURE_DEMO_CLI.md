# Azure CLI Demo Commands

Prepared values:

- Project: `Control room`
- Region: `West Europe`
- Frontend domain: Azure default URL only

Default resource names used:

- Resource group: `rg-control-room-demo-we`
- Backend App Service plan: `plan-control-room-demo-we`
- Backend app: `control-room-demo-api`
- Frontend static app: `control-room-demo-web`

Script:

- [deploy_azure_demo.ps1](deploy_azure_demo.ps1)

Before running it, replace only:

- `$GitHubRepoUrl`
- `$GitHubBranch`

Example:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy_azure_demo.ps1
```

Notes:

- The script creates the Azure resources and app settings.
- The frontend creation uses GitHub integration via `az staticwebapp create --login-with-github`.
- The backend creation sets `startup.txt`, which runs `python server.py`.
- After the resource creation, the backend code still needs to be deployed from the `backend/` folder.

Useful references:

- Azure Static Web Apps CLI create/appsettings:
  https://learn.microsoft.com/en-us/cli/azure/staticwebapp?view=azure-cli-latest
  https://learn.microsoft.com/en-us/cli/azure/staticwebapp/appsettings?view=azure-cli-latest
- Azure App Service plan/webapp/appsettings:
  https://learn.microsoft.com/en-us/cli/azure/appservice/plan?view=azure-cli-latest
  https://learn.microsoft.com/en-us/cli/azure/webapp?view=azure-cli-latest
  https://learn.microsoft.com/en-us/cli/azure/webapp/config/appsettings?view=azure-cli-latest
- Python startup on App Service:
  https://learn.microsoft.com/en-us/azure/developer/python/configure-python-web-app-on-app-service
