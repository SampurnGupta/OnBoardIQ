# OnboardIQ Cloud Run Deployment Guide

This guide provides copy-pasteable Google Cloud CLI commands for deploying OnboardIQ's microservice architecture to Google Cloud Run, fulfilling **Course Criterion 11**.

---

## Architecture Overview

```
                      +-----------------------------+
                      |       Google Cloud Run      |
                      |    (Streamlit UI: Port 8501)|
                      +--------------+--------------+
                                     | (IAM Token)
                                     v
+-----------------------------+--------------+-----------------------------+
|      Google Cloud Run       |              |      Google Cloud Run       |
| (FastAPI Blackboard: 8001)  |<-------------+  (CrewAI A2A Screener: 8003)|
+--------------+--------------+              +--------------+--------------+
               |                                            |
               v                                            v
+-----------------------------+              +-----------------------------+
|    Google Cloud Firestore   |              |       Google Cloud Run      |
|  (Serverless State Store)   |              |    (FastMCP Server: 8002)   |
+-----------------------------+              +-----------------------------+
```

---

## 1. Prerequisites & GCP Project Setup

Set your Google Cloud project and region:
```bash
# Set your active GCP project
export PROJECT_ID="your-project-id"
export REGION="asia-south1" # Or us-central1
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Enable required Google Cloud APIs
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    firestore.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com
```

---

## 2. Serverless Storage: Cloud Firestore Setup

Initialize Cloud Firestore in Native mode for transactional zoned state:
```bash
# Create Cloud Firestore database in Native mode
gcloud firestore databases create --location=$REGION --type=firestore-native
```

---

## 3. Secret Manager Configuration (Zero Secrets in Code)

Store sensitive keys securely in Google Cloud Secret Manager:
```bash
# Create secret for telemetry or LLM endpoints (never hardcode in git)
echo -n "https://cloud.langfuse.com/api/public/otel" | \
    gcloud secrets create ONBOARDIQ_OTEL_ENDPOINT --data-file=-

# Grant Secret Manager Accessor role to Cloud Run default compute service account
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding ONBOARDIQ_OTEL_ENDPOINT \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

---

## 4. Container Image Artifact Registry Setup

Create an Artifact Registry repository for OnboardIQ container images:
```bash
gcloud artifacts repositories create onboardiq-repo \
    --repository-format=docker \
    --location=$REGION \
    --description="Docker repository for OnboardIQ microservices"
```

Build and push the container images:
```bash
# 1. Blackboard Service
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/onboardiq-repo/blackboard-svc:latest \
    -f deploy/Dockerfile.blackboard .

# 2. FastMCP Tool Server
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/onboardiq-repo/mcp-tools:latest \
    -f deploy/Dockerfile.mcp .

# 3. CrewAI A2A Screening Service
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/onboardiq-repo/screening-crew:latest \
    -f deploy/Dockerfile.screening .

# 4. Streamlit Web Dashboard
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/onboardiq-repo/ui:latest \
    -f deploy/Dockerfile.ui .
```

---

## 5. Deploy Microservices to Cloud Run

> **Cost Control Best Practice:** Always pass `--min-instances 0` so services scale down to zero when idle, incurring \$0.00 cost during evaluation hiatus.

### Step 5.1: Deploy Blackboard Service
```bash
gcloud run deploy onboardiq-blackboard \
    --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/onboardiq-repo/blackboard-svc:latest \
    --platform managed \
    --allow-unauthenticated \
    --min-instances 0 \
    --max-instances 3 \
    --memory 512Mi \
    --set-env-vars BLACKBOARD_STORE_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
```
*Note down the Service URL, e.g., `https://onboardiq-blackboard-xyz.a.run.app`.*

### Step 5.2: Deploy CrewAI Screening Service
```bash
BLACKBOARD_URL=$(gcloud run services describe onboardiq-blackboard --format="value(status.url)")

gcloud run deploy onboardiq-screening \
    --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/onboardiq-repo/screening-crew:latest \
    --platform managed \
    --allow-unauthenticated \
    --min-instances 0 \
    --max-instances 3 \
    --memory 1Gi \
    --set-env-vars BLACKBOARD_URL=${BLACKBOARD_URL}
```
*Note down the Screening Service URL, e.g., `https://onboardiq-screening-xyz.a.run.app`.*

### Step 5.3: Deploy Streamlit UI Dashboard
```bash
A2A_URL=$(gcloud run services describe onboardiq-screening --format="value(status.url)")

gcloud run deploy onboardiq-ui \
    --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/onboardiq-repo/ui:latest \
    --platform managed \
    --allow-unauthenticated \
    --min-instances 0 \
    --max-instances 2 \
    --memory 1Gi \
    --port 8501 \
    --set-env-vars BLACKBOARD_URL=${BLACKBOARD_URL},A2A_SCREENING_URL=${A2A_URL}
```

---

## 6. Verification and Health Check

Verify all deployed services are healthy:
```bash
UI_URL=$(gcloud run services describe onboardiq-ui --format="value(status.url)")
echo "Open OnboardIQ UI in browser: $UI_URL"

# Test Blackboard Health
curl -s "${BLACKBOARD_URL}/health"
# Returns: {"status":"ok"}

# Test CrewAI Agent Card Discovery
curl -s "${A2A_URL}/.well-known/agent.json" | jq .
# Returns AgentCard schema with capabilities and protocol version
```

---

## 7. Clean-up / Teardown (Avoid Unexpected Charges)

When coursework viva defense is finished, delete services or retain on min-instances 0:
```bash
gcloud run services delete onboardiq-ui --quiet
gcloud run services delete onboardiq-screening --quiet
gcloud run services delete onboardiq-blackboard --quiet
```

