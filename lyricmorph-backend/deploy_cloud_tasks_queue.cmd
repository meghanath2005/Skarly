@echo off
setlocal

set PROJECT_ID=lyricmorph
set REGION=us-central1
set QUEUE_NAME=skarly-generation
set GCLOUD=C:\Users\yeshw\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd

call "%GCLOUD%" config set project %PROJECT_ID%
call "%GCLOUD%" services enable cloudtasks.googleapis.com run.googleapis.com cloudbuild.googleapis.com firestore.googleapis.com storage.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com
call "%GCLOUD%" tasks queues describe %QUEUE_NAME% --location=%REGION% >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  echo Cloud Tasks queue already exists: %QUEUE_NAME%
) else (
  call "%GCLOUD%" tasks queues create %QUEUE_NAME% --location=%REGION%
)

echo Done. Queue: %QUEUE_NAME% in %REGION%
