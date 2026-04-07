# Scan Feature Architecture

## System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     SCAN FEATURE WORKFLOW                       │
└─────────────────────────────────────────────────────────────────┘

1. TEST SETUP
   ┌─────────────────────┐
   │ Test Images (*.jpg) │
   │ ┌─────────────────┐ │
   │ │ receipt_*.jpg   │ │  ← Store in backend/samples/
   │ │ apple_*.jpg     │ │
   │ │ label_*.jpg     │ │
   └─────────────────────┘


2. BACKEND (Port 8000)
   ┌──────────────────────────────────────────────┐
   │        POST /api/v1/scan/sample              │
   │  ✓ ENABLE_SAMPLE_SCAN=true (configured)     │
   │  ✓ SAMPLE_IMAGES_DIR=samples (configured)   │
   └──────────────────────────────────────────────┘
            │
            ├─ Read image from backend/samples/
            │
            ├─ Extract mode: "receipt" / "food" / "tag"
            │
            └─→ HTTP POST to AI Service
                


3. AI SERVICE (Port 8001)
   ┌──────────────────────────────────────────────┐
   │    POST /scan/                               │
   │    (Currently handles detection)             │
   ├──────────────────────────────────────────────┤
   │ Response: {                                  │
   │   type: "receipt",                           │
   │   items: ["Food1", "Food2", ...],            │
   │   confidence: 0.92                           │
   │ }                                            │
   └──────────────────────────────────────────────┘
            │
            └─→ Return to Backend


4. BACKEND PROCESSING
   ┌──────────────────────────────────────────────┐
   │ Parse AI response: items = [...]             │
   │                                              │
   │ For each item:                               │
   │ ├─ Search database for matching Food         │
   │ ├─ Get avg_shelf_life_days                   │
   │ └─ Calculate expiry = today + shelf_life     │
   │                                              │
   │ Create InventoryItem records                 │
   └──────────────────────────────────────────────┘
            │
            └─→ (Optional) Save to Database


5. DATABASE (SQLite)
   ┌──────────────────────────────────────────────┐
   │ InventoryItem {                              │
   │   id: 1,                                     │
   │   user_id: "test-user",                      │
   │   food_id: 42,                               │
   │   date_added: 2026-04-06 12:30:00,           │
   │   expiry_date: 2026-04-09 00:00:00, ← AUTO  │
   │   status: "active"                           │
   │ }                                            │
   └──────────────────────────────────────────────┘


6. RESPONSE TO CLIENT
   ┌────────────────────────────────────────────────────┐
   │ {                                                  │
   │   "sample": "receipt_walmart.jpg",                 │
   │   "mode": "receipt",                               │
   │   "detected": {                                    │
   │       "type": "receipt",                           │
   │       "items": ["Core Power", "Chicken", ...],    │
   │       "confidence": 0.92                           │
   │   },                                               │
   │   "stored_count": 4,                               │
   │   "stored_items": [                                │
   │       { id, user_id, food_id, expiry_date, ... }  │
   │   ]                                                │
   │ }                                                  │
   └────────────────────────────────────────────────────┘
```

## Image Modes

| Mode | Input | Use | AI Focus |
|------|-------|-----|----------|
| `food` | Single food photo | Fresh produce, packaged items | Identify item type |
| `receipt` | Store receipt | Multiple items from purchase | Extract all line items |
| `tag` | Product label/packaging | Close-up of label | Extract text/dates |


## Data Flow - Detailed

### Input: Sample Receipt Image
```
Receipt contains:
- CORE POWER S (Protein Shake)
- MINA BSB CP (Chicken Breast)
- CHK BST BNLS (Chicken Breast)
- CHICKEN RIB
- PK SALT GDER (Salt/Seasoning)
```

### AI Service Processing
```
Input Image → Vision Model → Parse Text → 
→ Identify Food Items → Return Structure

{
  "type": "receipt",
  "items": [
    "Core Power Protein",
    "Chicken Breast",
    "Chicken Rib",
    "Salt"
  ],
  "confidence": 0.92
}
```

### Backend Database Lookup & Storage
```
For each detected item:

"Core Power Protein" 
  → Search: LIKE match in Food table
  → Found: id=42, name="Protein Shake", avg_shelf_life_days=7
  → Calculate: expiry = 2026-04-06 + 7 days = 2026-04-13
  → Store: InventoryItem(user_id, food_id=42, expiry_date=2026-04-13)

"Chicken Breast"
  → Search: LIKE match in Food table
  → Found: id=5, name="Chicken Breast", avg_shelf_life_days=3
  → Calculate: expiry = 2026-04-06 + 3 days = 2026-04-09
  → Store: InventoryItem(user_id, food_id=5, expiry_date=2026-04-09)
```

### Result: Inventory Updated
```
User "test-user" now has:
✓ Protein Shake (expires 2026-04-13)
✓ Chicken Breast (expires 2026-04-09)
✓ Chicken Rib (expires 2026-04-10)
✓ Salt (expires 2026-05-06)
```


## Testing Checklist

- [ ] Copy images to `backend/samples/`
- [ ] Verify `.env` has correct settings
- [ ] Start AI service: `cd ai-services && python main.py`
- [ ] Start backend: `cd backend && python -m uvicorn app.main:app --reload`
- [ ] Run test: `cd backend && python test_scan.py`
- [ ] Select option 1 (receipt without DB persistence)
- [ ] Verify AI returns detected items
- [ ] Try option 2 (with persistence) to save to database
- [ ] Check database has new InventoryItem records


## Current Limitations

✗ **NOT YET IMPLEMENTED**:
- Expiry date extraction from product labels
- Automatic date parsing (OCR)
- Confidence-based item filtering

✓ **WORKING**:
- Image upload and AI detection
- Food item identification
- Database storage with default shelf-life
- Multiple image modes (food/receipt/tag)


## Next Phase: Expiry Date Model

Once ready, the flow will be:

```
AI Service Response
    ↓
Parse detected items + dates from labels
    ↓
Use ML model to predict expiry dates
    ↓
Store actual predicted dates (not defaults)
    ↓
Better inventory tracking
```

---

**Setup Status**: ✅ Complete and ready to test!
