"""One-off script: extract the post-sáp-nhập (2025) "Phường Dĩ An" administrative
boundary from the nationwide ward-level GeoJSON the user dropped under `Shp/`.

`Shp/VN34TinhThanh/Việt Nam (phường xã) - 34.geojson` is a ~280 MB file covering
every commune/ward in Vietnam under the new 34-province structure — far too big
to ship in the repo or load in a browser. This script streams through it with
`ijson` (constant memory) and pulls out only the one feature we need
(`ma_xa == "25942"`, the merged ward that now covers our CVRP study area), then
writes it to `backend/data/di_an_boundary.geojson`, which the API and frontend
actually consume.

Run once whenever the source file changes:
    backend/.venv/Scripts/python.exe backend/scripts/prepare_context_layers.py
"""
from __future__ import annotations

import json
from pathlib import Path

import ijson

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_WARDS = REPO_ROOT / "Shp" / "VN34TinhThanh" / "Việt Nam (phường xã) - 34.geojson"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "di_an_boundary.geojson"

# "ma_xa" (ward code) for the new merged Phường Dĩ An, which absorbed the old
# An Bình + Dĩ An wards and part of Tân Đông Hiệp — see `sap_nhap` in the output.
TARGET_MA_XA = "25942"


def extract_ward(source: Path, target_ma_xa: str) -> dict:
    with source.open("rb") as f:
        for feature in ijson.items(f, "features.item", use_float=True):
            if feature.get("properties", {}).get("ma_xa") == target_ma_xa:
                return feature
    raise SystemExit(f"Không tìm thấy ma_xa={target_ma_xa} trong {source}")


def main() -> None:
    if not SOURCE_WARDS.exists():
        raise SystemExit(
            f"Không tìm thấy {SOURCE_WARDS}. File nguồn (Shp/) chỉ có trên máy local, "
            "không được commit vào git — chạy script này trên máy có sẵn Shp/ trước."
        )

    feature = extract_ward(SOURCE_WARDS, TARGET_MA_XA)
    props = feature["properties"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    feature_collection = {"type": "FeatureCollection", "features": [feature]}
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(feature_collection, f, ensure_ascii=False)

    summary = (
        f"Found: {props['ten_xa']} (ma_xa={props['ma_xa']}) merged from: {props['sap_nhap']}\n"
        f"Wrote {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size / 1024:.1f} KB)"
    )
    print(summary.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
