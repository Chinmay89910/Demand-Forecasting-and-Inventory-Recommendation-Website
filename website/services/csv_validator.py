import io
import csv
from datetime import datetime
from typing import Dict, Any, List

class SalesCsvValidator:
    """
    Validates uploaded sales CSV files for format, required headers,
    date types, and non-negative quantities.
    """
    REQUIRED_COLUMNS = ["date", "article", "quantity"]
    COLUMN_ALIASES = {
        "item": "article",
        "product": "article",
        "product_name": "article",
        "sku": "article",
        "qty": "quantity",
        "sales": "quantity",
        "units": "quantity",
        "y": "quantity",
        "timestamp": "date",
        "day": "date",
        "ds": "date",
    }

    def validate_and_parse(self, file_content: str, max_preview_rows: int = 50) -> Dict[str, Any]:
        reader = csv.reader(io.StringIO(file_content))
        rows = list(reader)
        if not rows:
            return {
                "valid": False,
                "error": "The uploaded CSV file is empty.",
                "total_rows": 0,
                "accepted_rows": 0,
                "rejected_rows": 0,
                "accepted_data": [],
                "errors": ["File is empty"],
            }

        # Header detection & normalization
        raw_header = [h.strip().lower() for h in rows[0]]
        normalized_header = [self.COLUMN_ALIASES.get(h, h) for h in raw_header]

        missing = [req for req in self.REQUIRED_COLUMNS if req not in normalized_header]
        if missing:
            return {
                "valid": False,
                "error": f"Missing required columns: {', '.join(missing)}. File must include date, article, and quantity.",
                "detected_columns": raw_header,
                "total_rows": len(rows) - 1,
                "accepted_rows": 0,
                "rejected_rows": len(rows) - 1,
                "accepted_data": [],
                "errors": [f"Header missing: {', '.join(missing)}"],
            }

        date_idx = normalized_header.index("date")
        article_idx = normalized_header.index("article")
        quantity_idx = normalized_header.index("quantity")
        price_idx = normalized_header.index("price") if "price" in normalized_header else (
            normalized_header.index("unit_price") if "unit_price" in normalized_header else None
        )

        accepted_data = []
        errors = []
        rejected_count = 0

        for row_idx, r in enumerate(rows[1:], start=2):
            if not r or all(c.strip() == "" for c in r):
                continue
            
            # Bound check
            if len(r) <= max(date_idx, article_idx, quantity_idx):
                errors.append(f"Row {row_idx}: Incomplete row with fewer columns than header.")
                rejected_count += 1
                continue

            raw_date = r[date_idx].strip()
            raw_article = r[article_idx].strip()
            raw_qty = r[quantity_idx].strip().replace(",", "")

            # 1. Validate date
            parsed_date = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    pass

            if not parsed_date:
                errors.append(f"Row {row_idx}: Invalid date '{raw_date}'. Expected YYYY-MM-DD.")
                rejected_count += 1
                continue

            # 2. Validate article
            if not raw_article:
                errors.append(f"Row {row_idx}: Article name cannot be blank.")
                rejected_count += 1
                continue

            # 3. Validate quantity
            try:
                qty_val = float(raw_qty)
                if qty_val < 0:
                    errors.append(f"Row {row_idx}: Negative quantity ({qty_val}) is not permitted.")
                    rejected_count += 1
                    continue
            except ValueError:
                errors.append(f"Row {row_idx}: Non-numeric quantity '{raw_qty}'.")
                rejected_count += 1
                continue

            # 4. Optional price
            price_val = 0.0
            if price_idx is not None and len(r) > price_idx:
                try:
                    price_val = float(r[price_idx].strip().replace("€", "").replace("$", ""))
                except ValueError:
                    price_val = 0.0

            accepted_data.append({
                "date": parsed_date,
                "article": raw_article,
                "quantity": qty_val,
                "price": price_val,
            })

        unique_skus = list(set(d["article"] for d in accepted_data))
        dates = [d["date"] for d in accepted_data]
        date_span = {"min": min(dates), "max": max(dates)} if dates else {"min": None, "max": None}

        # Calculate per-SKU summaries so users see product-level demand and volume results
        sku_map = {}
        for d in accepted_data:
            art = d["article"]
            if art not in sku_map:
                sku_map[art] = {"total_qty": 0.0, "count": 0, "prices": [], "dates": set()}
            sku_map[art]["total_qty"] += d["quantity"]
            sku_map[art]["count"] += 1
            sku_map[art]["dates"].add(d["date"])
            if d.get("price", 0.0) > 0:
                sku_map[art]["prices"].append(d["price"])

        sku_summaries = []
        for art, stats in sku_map.items():
            days = max(1, len(stats["dates"]))
            avg_daily = round(stats["total_qty"] / days, 1)
            avg_price = round(sum(stats["prices"]) / len(stats["prices"]), 2) if stats["prices"] else 0.0
            sku_summaries.append({
                "article": art,
                "total_sold": int(round(stats["total_qty"])),
                "days": days,
                "avg_daily": avg_daily,
                "unit_price": avg_price
            })

        return {
            "valid": len(accepted_data) > 0,
            "total_rows": len(rows) - 1,
            "accepted_rows": len(accepted_data),
            "rejected_rows": rejected_count,
            "unique_articles": len(unique_skus),
            "date_range": date_span,
            "sample_skus": unique_skus[:10],
            "sku_summaries": sku_summaries,
            "preview_data": accepted_data[:max_preview_rows],
            "accepted_data": accepted_data,
            "errors": errors[:25],
        }

csv_validator = SalesCsvValidator()

