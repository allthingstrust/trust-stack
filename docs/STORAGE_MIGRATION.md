# Storage Migration: Local Filesystem to S3

**Status:** Planning Phase
**Estimated Time:** 30-60 minutes
**Priority:** Optional (required for multi-instance/serverless deployment)
**Created:** 2025-01-13

---

## Table of Contents

1. [Overview](#overview)
2. [Current State](#current-state)
3. [Why Migrate?](#why-migrate)
4. [Migration Options](#migration-options)
5. [Implementation Guide](#implementation-guide)
6. [Testing & Validation](#testing--validation)
7. [Rollback Plan](#rollback-plan)
8. [Production Deployment](#production-deployment)

---

## Overview

This document provides instructions for migrating the Trust Stack web application's report storage from local filesystem to AWS S3 (or S3-compatible storage like MinIO, DigitalOcean Spaces, Google Cloud Storage).

**Current Storage:** File-based in `output/webapp_runs/`
**Target Storage:** AWS S3 bucket with configurable backend
**Affected Components:**
- `webapp/app.py` (run_analysis, show_history_page)
- New: `storage/report_storage.py`
- Configuration in `.env` and `config/settings.py`

---

## Current State

### File Structure
```
output/webapp_runs/{brand_id}_{timestamp}/
├── _run_data.json          # Complete analysis metadata
├── {brand_id}_{timestamp}_report.pdf
└── {brand_id}_{timestamp}_report.md
```

### How It Works Now
1. **Analysis Run** (`webapp/app.py:1176-1420`)
   - Generates reports to local filesystem
   - Saves metadata to `_run_data.json`
   - Stores PDF/MD paths in metadata

2. **History Page** (`webapp/app.py:1890-2097`)
   - Scans `output/webapp_runs/` for `_run_data.json` files
   - Loads metadata from disk
   - Provides direct file downloads

### Limitations
| Deployment Type | Works? | Notes |
|----------------|--------|-------|
| Single VPS/EC2 | ✅ Yes | Files persist, simplest approach |
| Docker (persistent volume) | ✅ Yes | Requires volume mount |
| Heroku | ❌ No | Ephemeral filesystem (~24hr lifespan) |
| Serverless (Lambda/Cloud Run) | ❌ No | Stateless containers |
| Horizontal Scaling (multiple instances) | ❌ No | Each instance has separate filesystem |
| Kubernetes (no PVC) | ❌ No | Pods are ephemeral |

---

## Why Migrate?

### Benefits of S3 Storage

1. **Works Everywhere**
   - Serverless (Lambda, Cloud Run)
   - Containers (Docker, Kubernetes)
   - Traditional servers
   - Multi-instance deployments

2. **Reliability**
   - 99.999999999% durability (AWS S3)
   - Automatic redundancy
   - No disk space limits

3. **Scalability**
   - No filesystem limits
   - Works with load balancers
   - Multiple app instances can share storage

4. **Cost**
   - ~$0.023/GB/month (S3 Standard)
   - ~$0.004/GB/month (S3 Glacier for archives)
   - Pay only for what you use

5. **Features**
   - Pre-signed URLs for secure downloads
   - Lifecycle policies (auto-archive old reports)
   - Versioning and backup
   - CDN integration (CloudFront)

### When NOT to Migrate

- **Single VPS deployment with no scaling plans:** Current approach works fine
- **Privacy concerns:** If data cannot leave your infrastructure
- **Cost constraints:** Very small budgets (though S3 is cheap)
- **Rapid local development:** Filesystem is faster for testing

---

## Migration Options

### Option A: S3-Only (Simplest)
**Time:** ~30 minutes
**Complexity:** Low

- Replace filesystem storage completely
- All new reports go to S3
- Existing reports stay on filesystem (manual migration optional)

**Pros:**
- Clean implementation
- No conditional logic
- Simplest to maintain

**Cons:**
- Requires S3 credentials in development
- Cannot run without S3 access

---

### Option B: Dual Mode (Recommended)
**Time:** ~45 minutes
**Complexity:** Medium

- Support both local and S3 via environment variable
- Switch backends with `STORAGE_BACKEND=local` or `s3`
- Abstract storage layer

**Pros:**
- Works in dev without S3
- Easy testing before production switch
- Gradual migration path
- Can switch back if issues

**Cons:**
- More code to maintain
- Requires abstraction layer

**Configuration:**
```bash
# .env
STORAGE_BACKEND=local  # or 's3'
S3_BUCKET=authenticity-ratio-reports  # only if backend=s3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_REGION=us-east-1
```

---

### Option C: Hybrid (Future-Proof)
**Time:** ~60 minutes
**Complexity:** High

- Save to BOTH local and S3
- Local for fast access
- S3 for backup and multi-instance support
- Automatic sync

**Pros:**
- Best of both worlds
- Instant local access
- Cloud backup
- Redundancy

**Cons:**
- Most complex
- Potential sync issues
- Higher storage costs

---

## Implementation Guide

### Recommended: Option B (Dual Mode)

#### Step 1: Add Dependencies (5 min)

**File:** `requirements.txt`
```bash
# Add after existing dependencies
boto3>=1.28.0
```

**Install:**
```bash
pip install boto3
```

---

#### Step 2: Create Storage Abstraction (15 min)

**File:** `storage/report_storage.py` (NEW)

```python
"""
Storage abstraction layer for report files
Supports local filesystem and S3
"""

import os
import json
import logging
from typing import Dict, List, Optional, BinaryIO
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends"""

    @abstractmethod
    def save_file(self, file_path: str, content: bytes, content_type: str = 'application/octet-stream') -> str:
        """Save file and return storage path/URL"""
        pass

    @abstractmethod
    def save_json(self, file_path: str, data: dict) -> str:
        """Save JSON data"""
        pass

    @abstractmethod
    def list_runs(self) -> List[Dict]:
        """List all analysis runs"""
        pass

    @abstractmethod
    def load_run_data(self, run_path: str) -> Dict:
        """Load run metadata"""
        pass

    @abstractmethod
    def get_download_url(self, file_path: str, filename: str) -> str:
        """Get download URL for file"""
        pass

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists"""
        pass


class LocalStorage(StorageBackend):
    """Local filesystem storage backend"""

    def __init__(self, base_dir: str = 'output/webapp_runs'):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def save_file(self, file_path: str, content: bytes, content_type: str = 'application/octet-stream') -> str:
        """Save file to local filesystem"""
        full_path = os.path.join(self.base_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Handle both bytes and file paths
        if isinstance(content, bytes):
            with open(full_path, 'wb') as f:
                f.write(content)
        else:
            # Assume it's a file path to copy from
            with open(content, 'rb') as src:
                with open(full_path, 'wb') as dst:
                    dst.write(src.read())

        return full_path

    def save_json(self, file_path: str, data: dict) -> str:
        """Save JSON to local filesystem"""
        content = json.dumps(data, indent=2, default=str).encode('utf-8')
        return self.save_file(file_path, content, 'application/json')

    def list_runs(self) -> List[Dict]:
        """List all analysis runs from filesystem"""
        import glob
        run_files = glob.glob(os.path.join(self.base_dir, '*', '_run_data.json'))

        runs = []
        for run_file in run_files:
            try:
                with open(run_file, 'r') as f:
                    run_data = json.load(f)
                    run_data['_storage_path'] = run_file
                    runs.append(run_data)
            except Exception as e:
                logger.warning(f"Failed to load {run_file}: {e}")

        return runs

    def load_run_data(self, run_path: str) -> Dict:
        """Load run metadata from filesystem"""
        with open(run_path, 'r') as f:
            return json.load(f)

    def get_download_url(self, file_path: str, filename: str) -> str:
        """Return local file path (for streamlit download_button)"""
        return file_path

    def file_exists(self, file_path: str) -> bool:
        """Check if file exists locally"""
        full_path = os.path.join(self.base_dir, file_path) if not os.path.isabs(file_path) else file_path
        return os.path.exists(full_path)


class S3Storage(StorageBackend):
    """AWS S3 storage backend"""

    def __init__(self, bucket: str, region: str = 'us-east-1', prefix: str = 'reports'):
        self.bucket = bucket
        self.region = region
        self.prefix = prefix
        self.s3_client = boto3.client('s3', region_name=region)

    def save_file(self, file_path: str, content: bytes, content_type: str = 'application/octet-stream') -> str:
        """Upload file to S3"""
        s3_key = f"{self.prefix}/{file_path}"

        # Handle both bytes and file paths
        if isinstance(content, bytes):
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=content,
                ContentType=content_type
            )
        else:
            # Assume it's a file path
            self.s3_client.upload_file(
                content,
                self.bucket,
                s3_key,
                ExtraArgs={'ContentType': content_type}
            )

        logger.info(f"Uploaded to S3: s3://{self.bucket}/{s3_key}")
        return f"s3://{self.bucket}/{s3_key}"

    def save_json(self, file_path: str, data: dict) -> str:
        """Save JSON to S3"""
        content = json.dumps(data, indent=2, default=str).encode('utf-8')
        return self.save_file(file_path, content, 'application/json')

    def list_runs(self) -> List[Dict]:
        """List all analysis runs from S3"""
        runs = []

        # List all metadata files
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=f"{self.prefix}/",
            )

            if 'Contents' not in response:
                return runs

            # Filter for _run_data.json files
            metadata_keys = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('_run_data.json')]

            for key in metadata_keys:
                try:
                    obj = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                    run_data = json.loads(obj['Body'].read())
                    run_data['_storage_path'] = key
                    runs.append(run_data)
                except Exception as e:
                    logger.warning(f"Failed to load {key}: {e}")

        except ClientError as e:
            logger.error(f"Failed to list S3 objects: {e}")

        return runs

    def load_run_data(self, run_path: str) -> Dict:
        """Load run metadata from S3"""
        # Extract key from s3:// URL if needed
        key = run_path.replace(f"s3://{self.bucket}/", "")

        obj = self.s3_client.get_object(Bucket=self.bucket, Key=key)
        return json.loads(obj['Body'].read())

    def get_download_url(self, file_path: str, filename: str, expiration: int = 3600) -> str:
        """Generate pre-signed URL for download"""
        # Extract key from s3:// URL if needed
        key = file_path.replace(f"s3://{self.bucket}/", "")

        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': key,
                    'ResponseContentDisposition': f'attachment; filename="{filename}"'
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return ""

    def file_exists(self, file_path: str) -> bool:
        """Check if file exists in S3"""
        key = file_path.replace(f"s3://{self.bucket}/", "")

        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


def get_storage_backend() -> StorageBackend:
    """
    Factory function to get configured storage backend

    Returns:
        StorageBackend instance based on environment config
    """
    from config.settings import SETTINGS

    backend = os.getenv('STORAGE_BACKEND', 'local').lower()

    if backend == 's3':
        bucket = os.getenv('S3_BUCKET')
        region = os.getenv('S3_REGION', 'us-east-1')

        if not bucket:
            logger.warning("S3_BUCKET not configured, falling back to local storage")
            return LocalStorage()

        return S3Storage(bucket=bucket, region=region)

    else:  # local
        return LocalStorage()
```

---

#### Step 3: Update Configuration (5 min)

**File:** `.env.example`
```bash
# Add these lines:

# Storage Backend Configuration
STORAGE_BACKEND=local  # Options: local, s3
S3_BUCKET=authenticity-ratio-reports
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
```

**File:** `config/settings.py`
```python
# Add these settings to the Settings class:

# Storage configuration
storage_backend: str = os.getenv('STORAGE_BACKEND', 'local')
s3_bucket: str = os.getenv('S3_BUCKET', '')
s3_region: str = os.getenv('S3_REGION', 'us-east-1')
```

---

#### Step 4: Update `run_analysis()` (10 min)

**File:** `webapp/app.py`

**Location:** Around line 1177 (in `run_analysis` function)

**Add import at top:**
```python
from storage.report_storage import get_storage_backend
```

**Replace file saving logic (around line 1390-1410):**

Find this code:
```python
# Generate PDF report
pdf_path = os.path.join(run_dir, f"{brand_id}_{run_id}_report.pdf")
pdf_generator.generate_report(scoring_report, pdf_path)

# Generate Markdown report
md_path = os.path.join(run_dir, f"{brand_id}_{run_id}_report.md")
md_generator = MarkdownGenerator()
md_generator.generate_report(scoring_report, md_path)

# Save run data
run_data = {
    'run_id': run_id,
    'brand_id': brand_id,
    'keywords': keywords,
    'sources': sources,
    'timestamp': datetime.now().isoformat(),
    'pdf_path': pdf_path,
    'md_path': md_path,
    'scoring_report': scoring_report,
    'total_items': len(normalized_content)
}

data_path = os.path.join(run_dir, '_run_data.json')
with open(data_path, 'w') as f:
    json.dump(run_data, f, indent=2, default=str)
```

Replace with:
```python
# Get storage backend
storage = get_storage_backend()

# Generate reports to temp files first
import tempfile
with tempfile.TemporaryDirectory() as temp_dir:
    # Generate PDF report
    temp_pdf = os.path.join(temp_dir, f"{brand_id}_{run_id}_report.pdf")
    pdf_generator.generate_report(scoring_report, temp_pdf)

    # Generate Markdown report
    temp_md = os.path.join(temp_dir, f"{brand_id}_{run_id}_report.md")
    md_generator = MarkdownGenerator()
    md_generator.generate_report(scoring_report, temp_md)

    # Upload to storage backend
    pdf_path = storage.save_file(
        f"{brand_id}_{run_id}/{brand_id}_{run_id}_report.pdf",
        temp_pdf,
        'application/pdf'
    )

    md_path = storage.save_file(
        f"{brand_id}_{run_id}/{brand_id}_{run_id}_report.md",
        temp_md,
        'text/markdown'
    )

# Save run metadata
run_data = {
    'run_id': run_id,
    'brand_id': brand_id,
    'keywords': keywords,
    'sources': sources,
    'timestamp': datetime.now().isoformat(),
    'pdf_path': pdf_path,
    'md_path': md_path,
    'scoring_report': scoring_report,
    'total_items': len(normalized_content)
}

# Save metadata to storage
metadata_path = storage.save_json(
    f"{brand_id}_{run_id}/_run_data.json",
    run_data
)
```

---

#### Step 5: Update `show_history_page()` (10 min)

**File:** `webapp/app.py`

**Location:** Around line 1890 (in `show_history_page` function)

**Replace history loading logic (around line 1897-1932):**

Find this code:
```python
# Find all past runs
output_dir = os.path.join(PROJECT_ROOT, 'output', 'webapp_runs')

if not os.path.exists(output_dir):
    st.info("📭 No analysis history found. Run your first analysis to get started!")
    if st.button("🚀 Run Your First Analysis"):
        st.session_state['page'] = 'analyze'
        st.rerun()
    return

# Scan for run data files
run_files = file_glob.glob(os.path.join(output_dir, '*', '_run_data.json'))

if not run_files:
    st.info("📭 No analysis history found. Run your first analysis to get started!")
    if st.button("🚀 Run Your First Analysis"):
        st.session_state['page'] = 'analyze'
        st.rerun()
    return

# Load and display runs
runs = []
for run_file in run_files:
    try:
        with open(run_file, 'r') as f:
            run_data = json.load(f)
            # Add file path for reference
            run_data['_file_path'] = run_file
            runs.append(run_data)
    except Exception as e:
        logger.warning(f"Failed to load run data from {run_file}: {e}")
        continue

if not runs:
    st.warning("⚠️ Found run files but couldn't load any valid data. The files may be corrupted.")
    return
```

Replace with:
```python
# Get storage backend
storage = get_storage_backend()

# Load all runs from storage
runs = storage.list_runs()

if not runs:
    st.info("📭 No analysis history found. Run your first analysis to get started!")
    if st.button("🚀 Run Your First Analysis"):
        st.session_state['page'] = 'analyze'
        st.rerun()
    return
```

**Replace download buttons (around line 2069-2095):**

Find this code:
```python
with download_col2:
    # PDF download
    pdf_path = run.get('pdf_path')
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as f:
            st.download_button(
                label="📄 PDF",
                data=f.read(),
                file_name=os.path.basename(pdf_path),
                mime="application/pdf",
                key=f"pdf_{idx}",
                width="stretch"
            )

with download_col3:
    # Markdown download
    md_path = run.get('md_path')
    if md_path and os.path.exists(md_path):
        with open(md_path, 'r') as f:
            st.download_button(
                label="📋 MD",
                data=f.read(),
                file_name=os.path.basename(md_path),
                mime="text/markdown",
                key=f"md_{idx}",
                width="stretch"
            )
```

Replace with:
```python
with download_col2:
    # PDF download
    pdf_path = run.get('pdf_path')
    if pdf_path and storage.file_exists(pdf_path):
        # For S3, use link_button with pre-signed URL
        # For local, read file content
        if isinstance(storage, S3Storage):
            url = storage.get_download_url(pdf_path, os.path.basename(pdf_path))
            if url:
                st.link_button("📄 PDF", url, width="stretch")
        else:
            with open(pdf_path, 'rb') as f:
                st.download_button(
                    label="📄 PDF",
                    data=f.read(),
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                    key=f"pdf_{idx}",
                    width="stretch"
                )

with download_col3:
    # Markdown download
    md_path = run.get('md_path')
    if md_path and storage.file_exists(md_path):
        if isinstance(storage, S3Storage):
            url = storage.get_download_url(md_path, os.path.basename(md_path))
            if url:
                st.link_button("📋 MD", url, width="stretch")
        else:
            with open(md_path, 'r') as f:
                st.download_button(
                    label="📋 MD",
                    data=f.read(),
                    file_name=os.path.basename(md_path),
                    mime="text/markdown",
                    key=f"md_{idx}",
                    width="stretch"
                )
```

**Add import at top of download section:**
```python
from storage.report_storage import S3Storage
```

---

#### Step 6: Create storage/ Directory

```bash
mkdir -p storage
touch storage/__init__.py
```

---

## Testing & Validation

### Local Testing (10 min)

1. **Test with Local Storage (Default)**
   ```bash
   # .env
   STORAGE_BACKEND=local

   # Run analysis
   streamlit run webapp/app.py
   ```

   ✅ Verify:
   - Analysis completes
   - Reports saved to `output/webapp_runs/`
   - History page shows run
   - Downloads work

2. **Test with S3 Storage**
   ```bash
   # Create S3 bucket first (AWS Console or CLI)
   aws s3 mb s3://authenticity-ratio-reports --region us-east-1

   # .env
   STORAGE_BACKEND=s3
   S3_BUCKET=authenticity-ratio-reports
   S3_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your_key
   AWS_SECRET_ACCESS_KEY=your_secret

   # Run analysis
   streamlit run webapp/app.py
   ```

   ✅ Verify:
   - Analysis completes
   - Reports uploaded to S3 (check AWS Console)
   - History page shows run
   - Downloads generate pre-signed URLs
   - URLs work and download files

3. **Test Switching Backends**
   - Run analysis with `STORAGE_BACKEND=local`
   - Change to `STORAGE_BACKEND=s3`
   - Verify history still shows local runs
   - Run new analysis
   - Verify both local and S3 runs appear in history

---

### AWS S3 Setup (One-Time)

**Option 1: AWS Console**
1. Go to AWS S3 Console
2. Click "Create bucket"
3. Name: `authenticity-ratio-reports`
4. Region: `us-east-1` (or your preferred region)
5. Block public access: **ON** (keep reports private)
6. Versioning: Optional
7. Create bucket

**Option 2: AWS CLI**
```bash
aws s3 mb s3://authenticity-ratio-reports --region us-east-1

# Set lifecycle policy (optional - auto-delete old reports)
aws s3api put-bucket-lifecycle-configuration \
  --bucket authenticity-ratio-reports \
  --lifecycle-configuration file://lifecycle.json
```

**lifecycle.json** (optional - auto-archive reports older than 90 days):
```json
{
  "Rules": [
    {
      "Id": "ArchiveOldReports",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
```

**IAM Policy** (minimum permissions needed):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:HeadObject"
      ],
      "Resource": [
        "arn:aws:s3:::authenticity-ratio-reports",
        "arn:aws:s3:::authenticity-ratio-reports/*"
      ]
    }
  ]
}
```

---

## Rollback Plan

If issues arise after migration:

### Immediate Rollback (< 1 minute)
```bash
# Change .env
STORAGE_BACKEND=local

# Restart app
# All new reports will save locally
# Existing S3 reports remain accessible
```

### Data Recovery
```bash
# Download all reports from S3
aws s3 sync s3://authenticity-ratio-reports output/webapp_runs/

# Switch back to local
STORAGE_BACKEND=local
```

---

## Production Deployment

### Recommended Deployment Path

1. **Phase 1: Development Testing** (Week 1)
   - Implement dual-mode storage
   - Test thoroughly with `STORAGE_BACKEND=local`
   - Test with development S3 bucket

2. **Phase 2: Staging** (Week 2)
   - Deploy to staging environment
   - Switch to `STORAGE_BACKEND=s3`
   - Run parallel testing (local + S3)
   - Validate all features

3. **Phase 3: Production Migration** (Week 3)
   - Create production S3 bucket
   - Configure IAM credentials
   - Deploy with `STORAGE_BACKEND=s3`
   - Monitor for 24 hours

4. **Phase 4: Cleanup** (Week 4+)
   - Optionally migrate old local reports to S3
   - Remove local storage code if stable
   - Document S3 bucket management

---

### Environment Variables by Environment

**Development:**
```bash
STORAGE_BACKEND=local
```

**Staging:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET=authenticity-ratio-reports-staging
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=${STAGING_AWS_KEY}
AWS_SECRET_ACCESS_KEY=${STAGING_AWS_SECRET}
```

**Production:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET=authenticity-ratio-reports-prod
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=${PROD_AWS_KEY}
AWS_SECRET_ACCESS_KEY=${PROD_AWS_SECRET}
```

---

### S3 Alternatives (Same Interface)

The storage abstraction supports any S3-compatible service:

**DigitalOcean Spaces:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET=my-space-name
S3_REGION=nyc3
AWS_ACCESS_KEY_ID=${DO_SPACES_KEY}
AWS_SECRET_ACCESS_KEY=${DO_SPACES_SECRET}
# Add custom endpoint in storage/report_storage.py:
# boto3.client('s3', endpoint_url='https://nyc3.digitaloceanspaces.com')
```

**MinIO (Self-Hosted):**
```bash
STORAGE_BACKEND=s3
S3_BUCKET=reports
AWS_ACCESS_KEY_ID=${MINIO_ACCESS_KEY}
AWS_SECRET_ACCESS_KEY=${MINIO_SECRET_KEY}
# Add custom endpoint in storage/report_storage.py:
# boto3.client('s3', endpoint_url='http://minio:9000')
```

**Google Cloud Storage:**
```bash
# Requires google-cloud-storage library + HMAC keys
STORAGE_BACKEND=s3
S3_BUCKET=gs://my-bucket
# Configure HMAC interoperability in GCS
```

---

## Migration Checklist

### Pre-Implementation
- [ ] Review current storage usage (`du -sh output/webapp_runs/`)
- [ ] Estimate monthly S3 costs (files × size × $0.023/GB)
- [ ] Decide on migration option (A, B, or C)
- [ ] Create AWS account (if needed)
- [ ] Set up IAM user with S3 permissions

### Implementation
- [ ] Install boto3 (`pip install boto3`)
- [ ] Create `storage/report_storage.py`
- [ ] Update `.env.example` and `config/settings.py`
- [ ] Update `run_analysis()` in `webapp/app.py`
- [ ] Update `show_history_page()` in `webapp/app.py`
- [ ] Create S3 bucket
- [ ] Configure IAM credentials

### Testing
- [ ] Test local storage mode
- [ ] Test S3 storage mode
- [ ] Test switching between backends
- [ ] Test downloads (local files)
- [ ] Test downloads (S3 pre-signed URLs)
- [ ] Test history page with mixed storage
- [ ] Load test (multiple concurrent analyses)

### Deployment
- [ ] Deploy to staging
- [ ] Run smoke tests
- [ ] Monitor logs for errors
- [ ] Deploy to production
- [ ] Monitor for 24 hours
- [ ] Document any issues

### Post-Migration
- [ ] Migrate old reports (optional)
- [ ] Set up S3 lifecycle policies
- [ ] Configure CloudWatch alarms (optional)
- [ ] Update runbooks/documentation
- [ ] Remove local storage code (optional)

---

## Cost Estimation

### S3 Standard Storage

**Assumptions:**
- 100 reports/month
- 2 MB per PDF + 500 KB per MD + 100 KB JSON = ~2.6 MB per report
- Total: 260 MB/month = 3.12 GB/year

**Costs:**
```
Storage: 3.12 GB × $0.023/GB = $0.07/month
Requests: 300 PUT + 1,000 GET = $0.01/month
Data Transfer: ~500 MB out = $0.04/month

Total: ~$0.12/month = $1.44/year
```

Negligible costs for typical usage! 🎉

---

## Troubleshooting

### Common Issues

**1. "NoCredentialsError: Unable to locate credentials"**
```bash
# Solution: Set AWS credentials
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret

# Or configure AWS CLI
aws configure
```

**2. "Access Denied" when uploading to S3**
```bash
# Solution: Check IAM policy has PutObject permission
# Verify bucket name is correct
# Check region matches
```

**3. Downloads not working in S3 mode**
```bash
# Solution: Check pre-signed URL generation
# Verify GetObject permission in IAM
# Check URL expiration (default 1 hour)
```

**4. History page shows no runs after switching to S3**
```bash
# Expected behavior - old local reports won't appear
# Solution: Keep STORAGE_BACKEND=local temporarily
# Or manually upload old reports to S3
```

---

## Future Enhancements

### Phase 2 Features (Optional)
1. **Report Deduplication**
   - Hash-based duplicate detection
   - Reference existing report if duplicate

2. **Automatic Archiving**
   - Move reports older than X days to S3 Glacier
   - Save 80% on storage costs

3. **CDN Integration**
   - CloudFront for faster global downloads
   - Reduced bandwidth costs

4. **Report Search**
   - Full-text search in metadata
   - Filter by date range, rating, keywords

5. **Batch Operations**
   - Bulk download multiple reports
   - Bulk delete old reports

---

## Questions & Support

### Getting Help
- **Implementation issues:** Check logs in webapp terminal
- **AWS issues:** Review CloudWatch logs, IAM policies
- **Code questions:** Review `storage/report_storage.py` docstrings

### Contact
- **Project Lead:** [Your Name]
- **AWS Admin:** [AWS Account Owner]
- **DevOps:** [Infrastructure Team]

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-13 | Claude | Initial documentation |

---

**Document Status:** ✅ Complete and ready for implementation
**Next Steps:** Review with team, approve migration option, schedule implementation
