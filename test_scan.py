#!/usr/bin/env python3
"""
Manual test script for the scan feature.
Use this to test images in the samples/ directory.
"""

import httpx
import json
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


BASE_URL = "http://localhost:8000/api/v1/scan"
SAMPLES_DIR = Path(__file__).parent / "samples"
FREEZER_STORABLE_KEYWORDS = {
    "chicken",
    "beef",
    "fish",
    "meat",
    "seafood",
    "pork",
    "shrimp",
    "salmon",
}


def list_samples():
    """List available sample images."""
    if not SAMPLES_DIR.exists():
        print(f"❌ Samples directory not found: {SAMPLES_DIR}")
        return []
    
    samples = list(SAMPLES_DIR.glob("*.jpg")) + list(SAMPLES_DIR.glob("*.jpeg"))
    if not samples:
        print(f"⚠️  No .jpg/.jpeg files in {SAMPLES_DIR}")
        return []
    
    print(f"\n📁 Available samples in {SAMPLES_DIR}:")
    for i, sample in enumerate(samples, 1):
        size_kb = sample.stat().st_size / 1024
        print(f"   {i}. {sample.name} ({size_kb:.1f} KB)")
    
    return [s.name for s in samples]


def test_sample(
    sample_name: str,
    mode: str = "receipt",
    persist_to_db: bool = False,
    user_id: str = "test-user",
    freezer_counts: dict[str, int] | None = None,
    manual_items: list[dict[str, int | str]] | None = None,
):
    """Test a sample image via the /sample endpoint."""
    
    sample_path = SAMPLES_DIR / sample_name
    if not sample_path.exists():
        print(f"❌ Sample not found: {sample_name}")
        print(f"   Expected at: {sample_path}")
        return None
    
    payload = {
        "sample_name": sample_name,
        "mode": mode,
        "persist_to_db": persist_to_db,
        "user_id": user_id if persist_to_db else None,
        "freezer_counts": freezer_counts or {},
        "manual_items": manual_items or [],
    }
    
    print(f"\n🔄 Testing: {sample_name}")
    print(f"   Mode: {mode}")
    print(f"   Persist to DB: {persist_to_db}")
    if persist_to_db:
        print(f"   User ID: {user_id}")
        if freezer_counts:
            print(f"   Freezer counts: {json.dumps(freezer_counts)}")
        if manual_items:
            print(f"   Manual items: {json.dumps(manual_items)}")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{BASE_URL}/sample", json=payload)
            response.raise_for_status()
        
        result = response.json()
        print("\n✅ Success!")
        print("\n📊 Result:")
        print(json.dumps(result, indent=2))
        
        if persist_to_db and result.get("stored_items"):
            print(f"\n✔️  Stored {result['stored_count']} items in database")
        
        return result
    
    except httpx.HTTPError as e:
        print(f"\n❌ Error: {e.response.status_code}")
        try:
            error = e.response.json()
            print(f"   Details: {error}")
        except ValueError:
            print(f"   Response: {e.response.text}")
        return None
    
    except Exception as e:
        print(f"\n❌ Connection error: {e}")
        print(f"   Make sure backend is running on {BASE_URL}")
        return None


def get_freezer_counts_from_preview(sample_name: str, mode: str) -> dict[str, int]:
    """Run a preview scan and ask how many of each item should go to the freezer."""
    preview = test_sample(sample_name, mode=mode, persist_to_db=False)
    if not preview:
        return {}

    detected_item_counts = preview.get("detected_item_counts", {})
    freezer_candidates = {
        name: count
        for name, count in detected_item_counts.items()
        if any(keyword in name.lower() for keyword in FREEZER_STORABLE_KEYWORDS)
    }
    return prompt_freezer_counts(freezer_candidates)


def prompt_freezer_counts(detected_item_counts: dict[str, int]) -> dict[str, int]:
    """Ask how many of each detected item should go to the freezer."""
    freezer_counts: dict[str, int] = {}

    if not detected_item_counts:
        print("\n🧊 No freezer-eligible items were detected.")
        return freezer_counts

    print("\n🧊 Freezer choice:")
    print("For each freezer-eligible item, enter how many should go to the freezer. Enter 0 if none.")

    for item_name, total_count in detected_item_counts.items():
        prompt = f"   {item_name} (detected {total_count}) -> freezer count [0-{total_count}]: "
        raw_value = input(prompt).strip()
        if not raw_value:
            freezer_counts[item_name] = 0
            continue
        try:
            freezer_value = int(raw_value)
        except ValueError:
            freezer_value = 0
        freezer_counts[item_name] = max(0, min(total_count, freezer_value))

    return freezer_counts


def get_tag_manual_items_from_preview(sample_name: str) -> list[dict[str, int | str]]:
    """Ask for tag item details after previewing the image."""
    preview = test_sample(sample_name, mode="tag", persist_to_db=False)
    if not preview:
        return []

    print("\n🏷️ Tag item details:")
    print("Enter the food name, quantity, and how many go to the freezer.")
    print("If you only want to keep it out of freezer, set freezer count to 0.")

    items: list[dict[str, int | str]] = []
    while True:
        food_name = input("   Food name (blank to finish): ").strip()
        if not food_name:
            break

        quantity_raw = input("   Quantity [1]: ").strip()
        freezer_raw = input("   Freezer count [0]: ").strip()

        try:
            quantity = max(1, int(quantity_raw)) if quantity_raw else 1
        except ValueError:
            quantity = 1

        try:
            freezer_count = max(0, int(freezer_raw)) if freezer_raw else 0
        except ValueError:
            freezer_count = 0

        freezer_count = min(quantity, freezer_count)
        items.append({"name": food_name, "quantity": quantity, "freezer_count": freezer_count})

    return items


def _run_preview_receipt(sample_name: str):
    preview_result = test_sample(sample_name, mode="receipt", persist_to_db=False)
    if preview_result and preview_result.get("detected_item_counts"):
        print("\nℹ️ Preview only: freezer choices below are not saved to the database.")
        freezer_counts = prompt_freezer_counts(preview_result["detected_item_counts"])
        if freezer_counts:
            print(f"\n🧊 Freezer summary: {json.dumps(freezer_counts)}")
            print("ℹ️ Run option 2 if you want the freezer counts to affect stored items.")


def _run_receipt_with_persistence(sample_name: str):
    user_id = input("Enter user ID [test-user]: ").strip() or "test-user"
    freezer_counts = get_freezer_counts_from_preview(sample_name, mode="receipt")
    test_sample(
        sample_name,
        mode="receipt",
        persist_to_db=True,
        user_id=user_id,
        freezer_counts=freezer_counts,
    )


def _run_food_preview(sample_name: str):
    test_sample(sample_name, mode="food", persist_to_db=False)


def _run_custom_test(sample_name: str):
    mode = input("Enter mode (receipt/food/tag) [receipt]: ").strip() or "receipt"
    persist = input("Persist to database? (y/n) [n]: ").strip().lower() == "y"
    user_id = "test-user"
    freezer_counts: dict[str, int] = {}
    manual_items: list[dict[str, int | str]] = []

    print("\n📝 Optional manual item details for this upload:")
    item_name = input("Enter item name (blank to skip): ").strip()
    quantity = 1
    if item_name:
        quantity_raw = input("Enter quantity [1]: ").strip()
        try:
            quantity = max(1, int(quantity_raw)) if quantity_raw else 1
        except ValueError:
            quantity = 1

        manual_items.append({"name": item_name, "quantity": quantity, "freezer_count": 0})

    if persist:
        user_id = input("Enter user ID [test-user]: ").strip() or "test-user"
        if mode == "tag":
            # Keep the manually entered name/quantity and add extra tag details if provided.
            manual_items.extend(get_tag_manual_items_from_preview(sample_name))
        else:
            freezer_counts = get_freezer_counts_from_preview(sample_name, mode=mode)
    test_sample(
        sample_name,
        mode=mode,
        persist_to_db=persist,
        user_id=user_id,
        freezer_counts=freezer_counts,
        manual_items=manual_items,
    )


def _print_menu():
    print("\n📋 Test Options:")
    print("   1. Preview receipt scan only")
    print("   2. Receipt scan + save non-freezer items")
    print("   3. Food scan only")
    print("   4. Custom test")
    print("   5. Exit")


def _get_sample_name(samples: list[str]) -> str:
    return input(f"\nEnter sample name [{samples[0]}]: ").strip() or samples[0]


def main():
    print("=" * 60)
    print("🍎 Scan Feature Test Script")
    print("=" * 60)
    
    # List available samples
    samples = list_samples()
    if not samples:
        print("\n💡 Tip: Add .jpg files to backend/samples/")
        sys.exit(1)
    
    _print_menu()
    
    choice = input("\nSelect option (1-5): ").strip()
    
    if choice == "1":
        _run_preview_receipt(_get_sample_name(samples))
    
    elif choice == "2":
        _run_receipt_with_persistence(_get_sample_name(samples))
    
    elif choice == "3":
        _run_food_preview(_get_sample_name(samples))
    
    elif choice == "4":
        _run_custom_test(_get_sample_name(samples))
    
    elif choice == "5":
        print("👋 Goodbye!")
        sys.exit(0)
    
    else:
        print("❌ Invalid option")
        sys.exit(1)


if __name__ == "__main__":
    main()
