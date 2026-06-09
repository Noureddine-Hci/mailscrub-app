---
description: Deploy the application to Google Cloud Run
---

This workflow standardizes the deployment process for MailScrub.

### Prerequisites
- Google Cloud SDK installed and configured (`gcloud auth login`)
- Project set to `mailscrub-app`

### 1. Build and Deploy
// turbo
```powershell
gcloud run deploy mailscrub-dashboard `
  --source . `
  --region europe-west1 `
  --project mailscrub-app `
  --allow-unauthenticated `
  --port 8080
```

> [!IMPORTANT]
> Ensure all required environment variables (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SECRET_KEY`) are set in the Cloud Run service configuration via the GCP Console or by adding `--set-env-vars` to the command above.
