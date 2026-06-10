---
description: Deploy the application to Azure Container Apps
---

This workflow standardizes the deployment process for MailScrub.

### Infrastructure (already provisioned)
- **Resource group** : `mailscrub-rg` (eastus)
- **Container Apps environment** : `mailscrub-env` (swedencentral)
- **Container App** : `mailscrub` (swedencentral)
- **Image registry** : `ghcr.io/noureddine-hci/mailscrub:latest`
- **Live URL** : https://mailscrub.gentlemushroom-a6aae85d.swedencentral.azurecontainerapps.io

### Prerequisites
- Azure CLI installed (`az version`)
- Logged in : `az login --tenant 108bc864-cdf5-4ec3-8b7c-4eb06be1b41d`
- Docker running in WSL Debian
- GitHub PAT with `write:packages` scope (for ghcr.io push)

### Deploy a new version

**1. Build & push the image (WSL Debian via PowerShell)**
```powershell
wsl -d Debian -- docker login ghcr.io -u Noureddine-Hci --password-stdin
# (enter PAT when prompted)

wsl -d Debian -- docker build -t ghcr.io/noureddine-hci/mailscrub:latest /mnt/c/Users/Noureddine/.gemini/antigravity/scratch/MailScrub
wsl -d Debian -- docker push ghcr.io/noureddine-hci/mailscrub:latest
```

**2. Redeploy the Container App (picks up the new image)**
```powershell
$env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH', 'User')
az containerapp update --name mailscrub --resource-group mailscrub-rg --image ghcr.io/noureddine-hci/mailscrub:latest
```

### Secrets (stored encrypted in Azure, never in the image)
Managed via `az containerapp secret set` — see SESSION-HANDOFF.md for details.

### Google OAuth
Authorized redirect URIs (Google Cloud Console → mailscrub-app → Credentials → MailScrub Web Client):
- `http://localhost:8000/auth/callback` (local dev)
- `https://mailscrub.app/auth/callback` (custom domain)
- `https://mailscrub.gentlemushroom-a6aae85d.swedencentral.azurecontainerapps.io/auth/callback` (Azure ACA)
