"""
Screenshot Capture Module

Captures full-page and above-fold screenshots using Playwright for visual analysis.
Integrates with the existing PlaywrightBrowserManager for efficient browser reuse.
"""

import io
import logging
import os
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path
import shutil

logger = logging.getLogger('ingestion.screenshot_capture')

# Optional boto3 import for S3 uploads
try:
    import boto3
    from botocore.exceptions import ClientError
    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False
    boto3 = None

# Optional Playwright import
try:
    from playwright.sync_api import Page
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    Page = None


# Default viewport configurations
VIEWPORT_DESKTOP = {"width": 1920, "height": 1080}
VIEWPORT_MOBILE = {"width": 375, "height": 812}


class ScreenshotCapture:
    """Captures screenshots of web pages for visual analysis."""

    def __init__(
        self,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "visual-analysis/",
        retention_hours: int = 24,
    ):
        """
        Initialize screenshot capture.

        Args:
            s3_bucket: S3 bucket for temporary storage (None to disable S3)
            s3_prefix: Prefix path in S3 bucket
            retention_hours: Hours before screenshots expire (for lifecycle policy)
        """
        self.s3_bucket = s3_bucket or os.getenv("SCREENSHOT_S3_BUCKET", "")
        self.report_bucket = os.getenv("REPORT_S3_BUCKET") or self.s3_bucket
        self.s3_prefix = s3_prefix
        self.retention_hours = retention_hours
        
        # Compression settings
        self.format = os.getenv("SCREENSHOT_FORMAT", "png").lower()
        if self.format not in ["png", "jpeg"]:
            logger.warning(f"Invalid SCREENSHOT_FORMAT '{self.format}', defaulting to 'png'")
            self.format = "png"
            
        self.quality = None
        if self.format == "jpeg":
            q_str = os.getenv("SCREENSHOT_QUALITY", "80")
            try:
                self.quality = int(q_str)
                self.quality = max(0, min(100, self.quality))
            except ValueError:
                logger.warning(f"Invalid SCREENSHOT_QUALITY '{q_str}', defaulting to 80")
                self.quality = 80
                
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy-load S3 client."""
        if self._s3_client is None and _BOTO3_AVAILABLE and self.s3_bucket:
            self._s3_client = boto3.client('s3')
        return self._s3_client

    def _dismiss_popups(self, page: "Page"):
        """
        Attempt to dismiss common popups (cookie banners, newsletters, etc.).
        
        Args:
            page: Playwright Page object
        """
        if not page:
            return
            
        logger.info("Attempting to dismiss popups...")
        
        # Common selectors for close buttons and "No thanks" links
        # Covering: generic close, cookie accept/reject, newsletter dismissal
        selectors = [
            "button[aria-label='Close']",
            "button[aria-label='close']",
            ".close-button",
            ".close-icon",
            "svg[data-icon='close']",
            "div[role='button'][aria-label='Close']",
            # Common text patterns (case insensitive matching in Playwright)
            "text=No Thanks",
            "text=No, thanks",
            "text=Not now",
            "text=Skip",
            "text=Accept All",
            "text=Accept Cookies", 
            "text=Reject All",
            "text=I accept",
            "button:has-text('Close')",
            "button:has-text('Accept')",
        ]
        
        for selector in selectors:
            try:
                # Check if visible and clickable
                if page.is_visible(selector, timeout=200):
                    logger.debug(f"Dismissing popup with selector: {selector}")
                    page.click(selector, timeout=500)
                    # Small wait to let animation finish
                    page.wait_for_timeout(200)
            except Exception:
                # Ignore errors (element not found, not clickable, etc.)
                continue

    def capture_screenshot(
        self,
        page: "Page",
        url: str,
        full_page: bool = True,
        viewport: Optional[Dict[str, int]] = None,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Capture a screenshot from an already-loaded Playwright page.

        Args:
            page: Playwright Page object (already navigated)
            url: URL of the page (for metadata)
            full_page: If True, capture full scrollable page; else just viewport
            viewport: Optional viewport override

        Returns:
            Tuple of (screenshot_bytes, metadata_dict)
        """
        if not _PLAYWRIGHT_AVAILABLE or page is None:
            logger.warning("Playwright not available or page is None")
            return b"", {"error": "Playwright not available"}

        metadata = {
            "url": url,
            "captured_at": datetime.utcnow().isoformat(),
            "full_page": full_page,
            "viewport": viewport or VIEWPORT_DESKTOP,
        }

        try:
            # Set viewport if specified
            if viewport:
                page.set_viewport_size(viewport)

            # Wait for any lazy-loaded content
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                # Network idle timeout is acceptable - content may still be loading
                pass

            # Dismiss popups before capture
            self._dismiss_popups(page)

            # Capture screenshot
            screenshot_args = {
                "type": self.format,
                "full_page": full_page,
            }
            if self.format == "jpeg" and self.quality is not None:
                screenshot_args["quality"] = self.quality
                
            screenshot_bytes = page.screenshot(**screenshot_args)

            metadata["size_bytes"] = len(screenshot_bytes)
            metadata["success"] = True

            logger.info(
                "Captured %s screenshot for %s (%d bytes)",
                "full-page" if full_page else "viewport",
                url,
                len(screenshot_bytes),
            )

            return screenshot_bytes, metadata

        except Exception as e:
            logger.error("Failed to capture screenshot for %s: %s", url, e)
            metadata["error"] = str(e)
            metadata["success"] = False
            return b"", metadata

    def capture_above_fold(
        self,
        page: "Page",
        url: str,
        viewport: Optional[Dict[str, int]] = None,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Capture only the above-fold (viewport) portion of the page.

        Faster than full-page capture, suitable for quick visual checks.

        Args:
            page: Playwright Page object
            url: URL of the page
            viewport: Optional viewport configuration

        Returns:
            Tuple of (screenshot_bytes, metadata_dict)
        """
        return self.capture_screenshot(
            page=page,
            url=url,
            full_page=False,
            viewport=viewport or VIEWPORT_DESKTOP,
        )

    def upload_to_s3(
        self,
        screenshot_bytes: bytes,
        url: str,
        run_id: str,
    ) -> Optional[str]:
        """
        Upload screenshot to S3 with automatic key generation.

        Args:
            screenshot_bytes: PNG screenshot data
            url: URL of the captured page
            run_id: Pipeline run ID for organization

        Returns:
            S3 key if successful, None otherwise
        """
        if not self.s3_bucket or not screenshot_bytes:
            return None

        if not _BOTO3_AVAILABLE:
            logger.warning("boto3 not available, skipping S3 upload")
            return None

        # Generate unique key from URL and timestamp
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        domain = urlparse(url).netloc.replace(".", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        ext = "jpg" if self.format == "jpeg" else "png"
        content_type = "image/jpeg" if self.format == "jpeg" else "image/png"
        
        s3_key = f"{self.s3_prefix}{run_id}/{domain}_{url_hash}_{timestamp}.{ext}"

        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=screenshot_bytes,
                ContentType=content_type,
                Metadata={
                    "source_url": url[:256],  # Limit metadata size
                    "run_id": run_id,
                },
            )
            logger.info("Uploaded screenshot to s3://%s/%s", self.s3_bucket, s3_key)
            return f"s3://{self.s3_bucket}/{s3_key}"
        except Exception as e:
            logger.error(f"Failed to upload screenshot to S3: {e}")
            return None

    def store_screenshot(
        self,
        screenshot_bytes: bytes,
        url: str,
        run_id: str,
    ) -> Optional[str]:
        """
        Store screenshot in S3 if configured, otherwise locally.
        
        Args:
            screenshot_bytes: PNG data
            url: Source URL
            run_id: Run ID
            
        Returns:
            URI (s3://... or file://...) or None if failed
        """
        # Try S3 first if configured
        if self.s3_bucket and _BOTO3_AVAILABLE:
            s3_uri = self.upload_to_s3(screenshot_bytes, url, run_id)
            if s3_uri:
                return s3_uri
                
        # Fallback to local storage
        try:
            # Create local directory: output/screenshots/<run_id>/
            base_dir = Path("output/screenshots") / run_id
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            domain = urlparse(url).netloc.replace(".", "_")
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            ext = "jpg" if self.format == "jpeg" else "png"
            filename = f"{domain}_{url_hash}_{timestamp}.{ext}"
            
            filepath = base_dir / filename
            with open(filepath, "wb") as f:
                f.write(screenshot_bytes)
                
            uri = f"file://{filepath.absolute()}"
            logger.info(f"Stored screenshot locally: {uri}")
            return uri
            
        except Exception as e:
            logger.error(f"Failed to store screenshot locally: {e}")
            return None

    def get_screenshot_bytes(self, path: str) -> Optional[bytes]:
        """
        Retrieve screenshot bytes from S3 or local file.
        
        Args:
            path: S3 key, full s3:// URI, file:// URI, or https:// URI
            
        Returns:
            Image bytes or None if failed
        """
        if not path:
            return None

        # Handle local files
        if path.startswith("file://"):
            try:
                local_path = Path(path.replace("file://", ""))
                if local_path.exists():
                    return local_path.read_bytes()
            except Exception as e:
                logger.error(f"Failed to read local screenshot {path}: {e}")
                return None

        # Handle S3
        if not _BOTO3_AVAILABLE:
            logger.warning("Boto3 not available, cannot retrieve screenshot from S3")
            return None
            
        try:
            bucket = self.s3_bucket
            key = path

            # Parse s3:// URI
            if path.startswith("s3://"):
                parts = path.replace("s3://", "").split("/", 1)
                if len(parts) == 2:
                    bucket, key = parts
            
            # Parse https:// URI
            elif path.startswith("https://") and ".s3.amazonaws.com/" in path:
                 parts = path.replace("https://", "").split(".s3.amazonaws.com/", 1)
                 bucket = parts[0]
                 key = parts[1]

            if not bucket:
                logger.error("S3 bucket not configured for retrieval.")
                return None

            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
            
        except Exception as e:
            logger.error(f"Failed to retrieve screenshot from S3 ({path}): {e}")
            return None

    def get_presigned_url(self, s3_key: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generate a pre-signed URL for an S3 screenshot.

        Args:
            s3_key: The S3 object key
            expires_in: URL expiration in seconds (default 1 hour)

        Returns:
            Pre-signed URL or None if failed
        """
        if not self.s3_bucket or not _BOTO3_AVAILABLE:
            return None

        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.s3_bucket, 'Key': s3_key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error("Failed to generate presigned URL: %s", e)
            return None

    def archive_report_image(self, path: str, run_id: str) -> str:
        """
        Copy a screenshot to the long-term 'report-images' folder.
        
        Args:
            path: Current path (s3:// or file://)
            run_id: Run ID for organization
            
        Returns:
            New path in report-images folder, or original path if copy failed
        """
        try:
            # Handle S3 (s3:// or https://)
            if (path.startswith("s3://") or (path.startswith("https://") and ".s3.amazonaws.com/" in path)) and self.s3_bucket and _BOTO3_AVAILABLE:
                # Parse source key
                if path.startswith("s3://"):
                     parts = path.replace("s3://", "").split("/", 1)
                     src_bucket, src_key = parts
                else:
                     parts = path.replace("https://", "").split(".s3.amazonaws.com/", 1)
                     src_bucket, src_key = parts[0], parts[1]
                
                # Define dest key
                filename = os.path.basename(src_key)
                dest_key = f"report-images/{run_id}/{filename}"
                
                # Copy object
                # Note: If buckets align, we copy. If different, we copy effectively.
                copy_source = {'Bucket': src_bucket, 'Key': src_key}
                
                # Check validation: Destination bucket must exist
                target_bucket = self.report_bucket
                
                self.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=target_bucket,
                    Key=dest_key,
                    ACL='public-read'
                )
                logger.info(f"Archived S3 image to {target_bucket}/{dest_key}")
                return f"https://{target_bucket}.s3.amazonaws.com/{dest_key}"
                
            # Handle Local
            elif path.startswith("file://"):
                src_path = Path(path.replace("file://", ""))
                if not src_path.exists():
                    return path
                    
                # Define dest path
                filename = src_path.name
                dest_dir = Path("output/report-images") / run_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / filename
                
                if src_path != dest_path:
                    shutil.copy2(src_path, dest_path)
                    logger.info(f"Archived local image to {dest_path}")
                    
                return f"file://{dest_path.absolute()}"
                
        except Exception as e:
            logger.warning(f"Failed to archive image {path}: {e}")
            
        return path



def should_capture_screenshot(content_type: str, source_type: str) -> bool:
    """
    Determine if visual analysis should be performed for this content.

    Based on approved scope: brand-owned and landing pages only.

    Args:
        content_type: Type of content (landing_page, blog, article, etc.)
        source_type: Source type (brand_owned, third_party, user_generated)

    Returns:
        True if visual analysis should be performed
    """
    # Get configured scope from environment
    scope_config = os.getenv("VISUAL_SCOPE", "brand_owned,landing_page")
    allowed_scopes = [s.strip().lower() for s in scope_config.split(",")]

    # Check if this content matches our scope
    if source_type.lower() in ["brand_owned", "brand-owned"]:
        return True

    if content_type.lower() in allowed_scopes:
        return True

    # Third-party and user-generated content is excluded
    if source_type.lower() in ["third_party", "third-party", "user_generated"]:
        return False

    return False


# Singleton instance
_SCREENSHOT_CAPTURE: Optional[ScreenshotCapture] = None


def get_screenshot_capture() -> ScreenshotCapture:
    """Get the global screenshot capture instance."""
    global _SCREENSHOT_CAPTURE
    if _SCREENSHOT_CAPTURE is None:
        _SCREENSHOT_CAPTURE = ScreenshotCapture(
            s3_bucket=os.getenv("SCREENSHOT_S3_BUCKET", ""),
            s3_prefix=os.getenv("SCREENSHOT_S3_PREFIX", "visual-analysis/"),
            retention_hours=int(os.getenv("SCREENSHOT_RETENTION_HOURS", "24")),
        )
    return _SCREENSHOT_CAPTURE
