# Phase 13: Cloud Run + Cloud Tasks Deployment Plan

## Goal

Deploy the Skarly FastAPI backend so saved creators use real Firebase Auth, Firestore, Cloud Storage, and backend-owned job execution outside the local machine.

## What Is Ready

- Backend Dockerfile installs FFmpeg and runs on Cloud Run's `$PORT`.
- Firebase Admin credentials are supported through environment/Cloud Run service account.
- Firestore mode is implemented.
- Google Cloud Storage signed upload/download URLs are implemented.
- Local task mode uses `SKARLY_TASK_BACKEND=inline`.
- Cloud Tasks dispatch mode is available through `SKARLY_TASK_BACKEND=cloud_tasks`.

## Google Cloud Setup

1. Enable APIs:
   - Cloud Run
   - Cloud Build
   - Cloud Tasks
   - Firestore
   - Cloud Storage

2. Create a Cloud Tasks queue:

```bat
gcloud tasks queues create skarly-generation --location=us-central1
```

Shortcut from the backend folder:

```bat
deploy_cloud_tasks_queue.cmd
```

3. Use a service account with these development permissions:
   - Cloud Datastore User
   - Storage Object User
   - Cloud Tasks Enqueuer
   - Cloud Run Invoker

4. Deploy backend to Cloud Run with real-service env values:

```bat
gcloud run deploy skarly-backend ^
  --source lyricmorph-backend ^
  --region us-central1 ^
  --allow-unauthenticated ^
  --set-env-vars SKARLY_ENV=production,AUTH_MODE=firebase_with_guest,FIREBASE_PROJECT_ID=lyricmorph,SKARLY_REPOSITORY_BACKEND=firestore,SKARLY_STORAGE_BACKEND=gcs,SKARLY_STORAGE_BUCKET=lyricmorph-user,SKARLY_WORKER_BACKEND=mvp_audio,SKARLY_MUSIC_GENERATOR_BACKEND=procedural_v2,SKARLY_TASK_BACKEND=cloud_tasks,SKARLY_CLOUD_TASKS_LOCATION=us-central1,SKARLY_CLOUD_TASKS_QUEUE=skarly-generation,SKARLY_WORKER_SHARED_SECRET=replace-with-secret,SKARLY_CORS_ORIGINS=https://your-frontend-domain
```

Shortcut from the backend folder:

```bat
set SKARLY_WORKER_SHARED_SECRET=replace-with-a-long-random-secret
deploy_cloud_run.cmd
```

5. After the first deploy returns a Cloud Run URL, update:

```bat
gcloud run services update skarly-backend ^
  --region us-central1 ^
  --update-env-vars SKARLY_TASK_BACKEND=cloud_tasks,SKARLY_PUBLIC_BACKEND_URL=https://YOUR-CLOUD-RUN-URL,SKARLY_WORKER_URL=https://YOUR-CLOUD-RUN-URL
```

## Frontend Change After Deploy

Update the Expo app backend base URL from local:

```text
http://127.0.0.1:8090
```

to the deployed Cloud Run URL.

In `lyricmorph-mobile\.env`:

```text
EXPO_PUBLIC_BACKEND_BASE_URL=https://YOUR-CLOUD-RUN-URL
```

## Smoke Checks

```bat
curl https://YOUR-CLOUD-RUN-URL/health
```

Expected:

```json
{
  "ok": true,
  "service": "skarly-backend",
  "phase": 12,
  "repository_backend": "firestore",
  "storage_backend": "gcs",
  "worker_backend": "mvp_audio",
  "task_backend": "cloud_tasks"
}
```

## Still Pending After Deployment

- Real AI music generation beyond the simple MVP backing bed.
- Production-grade queue retry policy and dead-letter handling.
- Production domain for the Expo/web frontend.
- Secret Manager for `SKARLY_WORKER_SHARED_SECRET`.
