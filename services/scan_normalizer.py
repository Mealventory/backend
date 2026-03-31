import re

def normalize_scan_result(raw_data):
    items = []


    if "text" in raw_data:
        text = raw_data["text"].lower()


        parts = re.split(r',|\n', text)

        for part in parts:
            part = part.strip()
            if not part:
                continue


            match = re.match(r'(\d+)\s*([a-zA-Z]+)', part)
            if match:
                quantity, name = match.groups()
                items.append({
                    "name": name.capitalize(),
                    "quantity": float(quantity),
                    "unit": "units",
                    "confidence": 0.9
                })
                continue

            match = re.match(r'([a-zA-Z]+)\s*(\d+)([a-zA-Z]*)', part)
            if match:
                name, quantity, unit = match.groups()
                items.append({
                    "name": name.capitalize(),
                    "quantity": float(quantity),
                    "unit": normalize_unit(unit),
                    "confidence": 0.9
                })
                continue

       
            match = re.match(r'(\d+)\s*x\s*([a-zA-Z]+)', part)
            if match:
                quantity, name = match.groups()
                items.append({
                    "name": name.capitalize(),
                    "quantity": float(quantity),
                    "unit": "units",
                    "confidence": 0.9
                })
                continue


            match = re.match(r'(\d+)([a-zA-Z]+)\s*([a-zA-Z]+)', part)
            if match:
                quantity, unit, name = match.groups()
                items.append({
                    "name": name.capitalize(),
                    "quantity": float(quantity),
                    "unit": normalize_unit(unit),
                    "confidence": 0.9
                })
                continue


            items.append({
                "name": part.capitalize(),
                "quantity": 1.0,
                "unit": "units",
                "confidence": 0.7
            })


    elif "items" in raw_data:
        for item in raw_data["items"]:
            items.append({
                "name": item.get("name", "").capitalize(),
                "quantity": float(item.get("qty", 1)),
                "unit": normalize_unit(item.get("unit", "")),
                "confidence": item.get("confidence", 0.9)
            })

    return {"items": items}


def normalize_unit(unit):
    unit = (unit or "").lower()

    if unit in ["l", "litre", "litres"]:
        return "litres"
    if unit in ["kg", "kilogram"]:
        return "kg"
    if unit in ["g", "gram"]:
        return "g"
    if unit in ["", None]:
        return "units"

    return unit