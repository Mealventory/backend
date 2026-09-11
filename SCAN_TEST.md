# Scan Feature - Setup & Testing Guide

## Quick Summary
- Store test images in `backend/samples/` folder
- Run AI service on port 8001
- Run backend on port 8000
- Test with interactive script
- Images get sent to Google Vision API → returns detected food items → stored in database

---

## 🖼️ Step 1: Copy Your Test Images to Backend

**Where to put them:**
```
backend/samples/
├── receipt_walmart.jpg
├── apple_photo1.jpg
├── apple_photo2.jpg
└── protein_shake_label.jpg
```

**File requirements:**
- Format: `.jpg` or `.jpeg` only
- Any size (up to 5MB tested)
- Color images work best

**How to copy (Windows PowerShell):**
```powershell
cd c:\Users\pablo\Documents\Capstone\backend

# Create folder if missing
mkdir samples -ErrorAction SilentlyContinue

# Copy your images
Copy-Item "C:\path\to\receipt.jpg" "samples\receipt_walmart.jpg"
Copy-Item "C:\path\to\apple1.jpg" "samples\apple_photo1.jpg"
Copy-Item "C:\path\to\apple2.jpg" "samples\apple_photo2.jpg"
Copy-Item "C:\path\to\shake_label.jpg" "samples\protein_shake_label.jpg"
```

**Verify:**
```powershell
dir backend\samples\
# Should show your 4 .jpg files
```

---

## 🚀 Step 2: Start Services (3 terminals)

### Terminal 1 - AI Service (MUST START FIRST)
```bash
cd \ai-services
python main.py
```
✓ Should show: `Uvicorn running on http://0.0.0.0:8001`

### Terminal 2 - Backend
```bash
cd \backend
python -m app.main (or python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload)
```
✓ Should show: `Uvicorn running on http://0.0.0.0:8000`

### Terminal 3 - Ready for testing
```bash
cd \backend
```

---

## 🧪 Step 3: Test the Scan Feature

### Option A: Interactive Test Script (Easiest)

```bash
python test_scan.py
```

**Menu:**
```
1. Test receipt scanning (no persistence) ← START HERE
2. Test receipt scanning (with persistence)
3. Test food item scanning (no persistence)
4. Custom test
5. Exit
```

**First test:** Press `1` → Enter `receipt_walmart.jpg`

### Option B: Manual curl Command

```bash
curl -X POST http://localhost:8000/api/v1/scan/sample \
  -H "Content-Type: application/json" \
  -d '{
    "sample_name": "receipt_walmart.jpg",
    "mode": "receipt",
    "persist_to_db": false
  }'
```

---

## ✅ Expected Results

If everything works, you'll see:

```json
{
  "sample": "receipt_walmart.jpg",
  "mode": "receipt",
  "detected": {
    "type": "receipt",
    "items": [
      "Core Power Protein",
      "Chicken Breast",
      "Chicken Rib",
      "Park Salt"
    ],
    "confidence": 0.92
  },
  "stored_count": 0,
  "stored_items": []
}
```

**What this means:**
- ✅ Image loaded from `samples/` folder
- ✅ Sent to AI service (Google Vision)
- ✅ AI correctly identified 4 food items from receipt
- ✅ Response returned with confidence score

---

## 💾 Test With Database Storage

Run `python test_scan.py` again and select option `2`:
- Enter user ID: `test-user`
- Same image will be tested
- Items will be stored in database with auto-calculated expiry dates

Response will show:
```json
{
  "stored_count": 4,
  "stored_items": [
    {
      "id": 1,
      "user_id": "test-user",
      "food_id": 42,
      "date_added": "2026-04-06T12:30:00",
      "expiry_date": "2026-04-09T00:00:00",
      "status": "active"
    }
  ]
}
```

---

## 🎯 Image Modes Explained

| Mode | Use For | Example |
|------|---------|---------|
| `receipt` | Store receipts with multiple items | Walmart receipt |
| `food` | Direct photo of single item | Apple, banana, fresh fruit |
| `tag` | Product label/packaging close-ups | Protein shake label |

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused (port 8001) | Start AI service first in Terminal 1 |
| "Sample not found" | Copy images to `backend/samples/` exactly |
| "Selected mode does not match image" | Use `receipt` for store receipts, `food` for items |
| "No food items detected" | Try different image, check lighting/quality |
| Tests bypass auth (no login needed) | `/sample` endpoint is for development only |

---

## 📊 What's Happening Behind the Scenes

```
1. Image uploaded to backend → Loaded from backend/samples/
2. Backend calls AI service → POST to http://127.0.0.1:8001/scan/
3. AI service runs Google Vision API → Detects food items
4. Backend receives response → Parses detected items list
5. Backend searches database → Matches items to Food table
6. Backend calculates expiry → Today + avg_shelf_life_days
7. Database stores → Creates InventoryItem records
8. Response sent back → Shows what was detected + stored
```

---

## ✨ Current vs Future

**✅ Working Now:**
- Food detection from images (receipts, photos, labels)
- Item identification and database storage
- Auto shelf-life calculation
- Database persistence

**⏳ Coming Later:**
- Expiry date prediction from images
- Automatic date extraction/OCR
- Confidence-based filtering

---

## ⚙️ Configuration Already Set

Your `.env` is ready:
```env
AI_SERVICE_URL=http://127.0.0.1:8001    # AI service location
ENABLE_SAMPLE_SCAN=true                 # Sample endpoint enabled
SAMPLE_IMAGES_DIR=samples               # Where test images are
DATABASE_URL=sqlite:///./local_test.db  # Local test database
```

---

## 🎓 Summary: How to Test

1. **Copy images** → `backend/samples/`
2. **Start AI service** → `cd ai-services && python main.py` (port 8001)
3. **Start backend** → `cd backend && python -m uvicorn app.main:app --reload` (port 8000)
4. **Run test** → `cd backend && python test_scan.py`
5. **Select option 1** → Enter image name when prompted
6. **View results** → JSON response shows detected items

**Done!** ✅
