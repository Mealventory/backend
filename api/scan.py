from fastapi import APIRouter, UploadFile, File
from services.scan_normalizer import normalize_scan_result
from google.cloud import vision
from io import BytesIO
import os

# Set up Google Vision client
#os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "path_to_your_google_vision_api_key.json"
#client = vision.ImageAnnotatorClient()
client = vision.ImageAnnotatorClient.from_service_account_file(
    r"D:\Mealventory\mealventory_backend\mealventory-ai-345622393f04.json"
)

router = APIRouter()

# Helper function to extract text from image
def extract_text_from_image(image_bytes: BytesIO):
    image = vision.Image(content=image_bytes.read())
    response = client.text_detection(image=image)
    return response.text_annotations[0].description if response.text_annotations else ""

@router.post("/")
async def scan_image(file: UploadFile = File(...)):
    # Read the image file into memory
    image_bytes = await file.read()

    # Extract text from the image using Google Vision API
    extracted_text = extract_text_from_image(BytesIO(image_bytes))
    
    # Normalize the extracted text (your scan normalization logic)
    normalized_data = normalize_scan_result({"text": extracted_text})

    return normalized_data