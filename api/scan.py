from fastapi import APIRouter, UploadFile, File, HTTPException
from services.scan_normalizer import normalize_scan_result
from io import BytesIO
from functools import lru_cache

router = APIRouter()


@lru_cache(maxsize=1)
def get_vision_client():
    # Use Application Default Credentials, including GOOGLE_APPLICATION_CREDENTIALS.
    # Initialize only for OCR so normalization and application startup work offline.
    try:
        from google.cloud import vision
        return vision.ImageAnnotatorClient()
    except (ImportError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Google Vision OCR is not configured") from exc
    except Exception as exc:
        from google.auth.exceptions import DefaultCredentialsError
        if isinstance(exc, DefaultCredentialsError):
            raise HTTPException(status_code=503, detail="Google Vision OCR is not configured") from exc
        raise


def extract_text_from_image(image_bytes: BytesIO):
    client = get_vision_client()
    from google.cloud import vision
    image = vision.Image(content=image_bytes.read())
    response = client.text_detection(image=image)
    if response.error.message:
        raise HTTPException(status_code=502, detail="Google Vision OCR request failed")
    return response.text_annotations[0].description if response.text_annotations else ""


@router.post("/scan/normalize")
def normalize_scan(data: dict):
    return normalize_scan_result(data)


@router.post("/")
def scan_image(file: UploadFile = File(...)):
    extracted_text = extract_text_from_image(file.file)
    return normalize_scan_result({"text": extracted_text})
