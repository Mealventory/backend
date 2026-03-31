from fastapi import APIRouter
from services.scan_normalizer import normalize_scan_result

router = APIRouter()

@router.post("/scan/normalize")
def normalize_scan(data: dict):
    result = normalize_scan_result(data)
    return result