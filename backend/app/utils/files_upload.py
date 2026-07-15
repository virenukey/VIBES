
import boto3
import uuid
import os
import io
import logging
from fastapi import UploadFile, HTTPException
from PIL import Image
from app.core.config import settings 

logger = logging.getLogger(__name__)

USE_S3                = settings.USE_S3
S3_BUCKET             = settings.S3_BUCKET
S3_REGION             = settings.S3_REGION
AWS_ACCESS_KEY_ID     = settings.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = settings.AWS_SECRET_ACCESS_KEY
LOCAL_UPLOAD_DIR      = settings.LOCAL_UPLOAD_DIR
BASE_URL              = settings.BASE_URL


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS    = {"jpg", "jpeg", "png", "webp"}
MAX_SIZE_MB           = 5

s3_client = None
if USE_S3:
    s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


async def upload_wastage_photo(file: UploadFile) -> str:
    """
    Validate and upload a wastage photo.
    Returns the public URL string.
    All validations run BEFORE any DB transaction.
    """

    # 1. Content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file.content_type}'. Allowed: jpeg, png, webp"
        )

    # 2. Extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extension '.{ext}'. Allowed: {ALLOWED_EXTENSIONS}"
        )

    # 3. Read bytes
    try:
        contents = await file.read()
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    # 4. Empty check
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # 5. Size check
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {size_mb:.1f}MB. Maximum: {MAX_SIZE_MB}MB"
        )

    # 6. Real image check via PIL
    try:
        img = Image.open(io.BytesIO(contents))
        img.verify()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid or corrupted image file"
        )

    # 7. Unique filename — no collisions ever
    unique_filename = f"wastage/{uuid.uuid4()}.{ext}"

    # 8. Upload to S3 or save locally
    if USE_S3:
        return _upload_to_s3(contents, unique_filename, file.content_type)
    else:
        return _save_locally(contents, unique_filename)


def _upload_to_s3(contents: bytes, filename: str, content_type: str) -> str:
    """Upload bytes to S3, return public URL."""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=filename,
            Body=contents,
            ContentType=content_type,
        )
        url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{filename}"
        logger.info(f"Photo uploaded to S3: {url}")
        return url
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to upload photo to S3")


def _save_locally(contents: bytes, filename: str) -> str:
    """Save bytes to local disk, return accessible URL."""
    try:
        save_dir = os.path.join(LOCAL_UPLOAD_DIR, "wastage")
        os.makedirs(save_dir, exist_ok=True)

        just_filename = filename.split("/")[-1]
        filepath = os.path.join(save_dir, just_filename)

        with open(filepath, "wb") as f:
            f.write(contents)

        url = f"{BASE_URL}/static/uploads/wastage/{just_filename}"
        logger.info(f"Photo saved locally: {filepath}")
        return url
    except Exception as e:
        logger.error(f"Local file save failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save photo to disk")

def get_presigned_url(s3_url: str, expiry: int = 60) -> str:
    """Convert private S3 URL to temporary presigned URL."""
    if not s3_url:
        return s3_url
    
    # ← if localhost URL, return as-is (old records)
    if "amazonaws.com" not in s3_url:
        return s3_url

    if not USE_S3:
        return s3_url

    try:
        # Extract key from URL
        # "https://bucket.s3.region.amazonaws.com/wastage/abc.jpg" → "wastage/abc.jpg"
        key = s3_url.split(".amazonaws.com/")[-1]

        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=expiry,
        )
    except Exception as e:
        return s3_url  # fallback to original URL 
    
async def handle_wastage_photo(photo: UploadFile | None) -> str | None:
    """Validate and upload a wastage photo. Returns URL or None."""
    if not photo:
        return None

    # Validate content type
    if photo.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: jpg, png, webp")

    contents = await photo.read()

    # Validate size
    if len(contents) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large. Max size: {MAX_SIZE_MB}MB")

    # Build unique filename
    ext = photo.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension")

    filename = f"wastage/{uuid.uuid4().hex}.{ext}"

    if USE_S3:
        return _upload_to_s3(contents, filename, photo.content_type)
    return _save_locally(contents, filename)    