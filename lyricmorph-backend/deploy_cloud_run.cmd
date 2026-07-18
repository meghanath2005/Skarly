@echo off
setlocal

set PROJECT_ID=lyricmorph
set REGION=us-central1
set SERVICE_NAME=skarly-backend
set BUCKET=lyricmorph-user
set QUEUE_NAME=skarly-generation
set FRONTEND_ORIGIN=http://localhost:8082
set ADMIN_EMAILS=yeshwant_satyada@srmap.edu.in
set ADMIN_UIDS=64EbLsRLTmflRHae5oJgrqQFs8f1
set GCS_SIGNING_SERVICE_ACCOUNT=293181449428-compute@developer.gserviceaccount.com
set GCLOUD=C:\Users\yeshw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd

if "%SKARLY_WORKER_SHARED_SECRET%"=="" (
  echo Set SKARLY_WORKER_SHARED_SECRET before deploying.
  echo Example: set SKARLY_WORKER_SHARED_SECRET=replace-with-a-long-random-secret
  exit /b 1
)

call "%GCLOUD%" config set project %PROJECT_ID%
call "%GCLOUD%" run deploy %SERVICE_NAME% ^
  --source . ^
  --region %REGION% ^
  --allow-unauthenticated ^
  --set-env-vars SKARLY_ENV=production,AUTH_MODE=firebase_with_guest,FIREBASE_PROJECT_ID=%PROJECT_ID%,SKARLY_ADMIN_EMAILS=%ADMIN_EMAILS%,SKARLY_ADMIN_UIDS=%ADMIN_UIDS%,SKARLY_REPOSITORY_BACKEND=firestore,SKARLY_STORAGE_BACKEND=gcs,SKARLY_STORAGE_BUCKET=%BUCKET%,SKARLY_GCS_SIGNING_SERVICE_ACCOUNT=%GCS_SIGNING_SERVICE_ACCOUNT%,SKARLY_WORKER_BACKEND=mvp_audio,SKARLY_MUSIC_GENERATOR_BACKEND=lyria,SKARLY_LYRIA_MODEL=lyria-3-clip-preview,SKARLY_LYRIA_FALLBACK_TO_PROCEDURAL=true,SKARLY_LYRIA_MONTHLY_LIMIT=25,SKARLY_LYRIA_UNIT_COST_USD=0.04,SKARLY_TASK_BACKEND=inline,SKARLY_CLOUD_TASKS_LOCATION=%REGION%,SKARLY_CLOUD_TASKS_QUEUE=%QUEUE_NAME%,SKARLY_WORKER_SHARED_SECRET=%SKARLY_WORKER_SHARED_SECRET%,SKARLY_CORS_ORIGINS=%FRONTEND_ORIGIN%

for /f "tokens=*" %%i in ('call "%GCLOUD%" run services describe %SERVICE_NAME% --region %REGION% --format "value(status.url)"') do set SERVICE_URL=%%i

if "%SERVICE_URL%"=="" (
  echo Could not read Cloud Run URL.
  exit /b 1
)

call "%GCLOUD%" run services update %SERVICE_NAME% ^
  --region %REGION% ^
  --update-env-vars SKARLY_TASK_BACKEND=cloud_tasks,SKARLY_PUBLIC_BACKEND_URL=%SERVICE_URL%,SKARLY_WORKER_URL=%SERVICE_URL%

echo Deployed %SERVICE_NAME% at %SERVICE_URL%
echo Put this in lyricmorph-mobile\.env:
echo EXPO_PUBLIC_BACKEND_BASE_URL=%SERVICE_URL%
