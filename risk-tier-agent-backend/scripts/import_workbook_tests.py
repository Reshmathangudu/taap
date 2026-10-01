# from __future__ import annotations

# import argparse
# from collections import defaultdict
# from pathlib import Path
# from typing import Any

# from openpyxl import load_workbook

# from app.repositories.test_repository import TestRepository


# def sheet_rows(workbook_path: Path, sheet_name: str) -> list[dict[str, Any]]:
#     workbook = load_workbook(workbook_path, read_only=True, data_only=True)
#     sheet = workbook[sheet_name]
#     iterator = sheet.iter_rows(values_only=True)
#     headers = [str(value).strip() for value in next(iterator)]
#     return [dict(zip(headers, row)) for row in iterator if any(value is not None for value in row)]


# def derive_test_story_mapping(workbook_path: Path) -> dict[str, str]:
#     requirements = sheet_rows(workbook_path, "04_Requirements")
#     mapping: dict[str, str] = {}
#     for row in requirements:
#         requirement_id = str(row.get("Requirement_ID") or "").strip()
#         story_id = str(row.get("Story_ID") or "").strip()
#         if requirement_id and story_id:
#             mapping[requirement_id] = story_id
#     return mapping


# def main() -> None:
#     parser = argparse.ArgumentParser()
#     parser.add_argument("workbook")
#     parser.add_argument("--db", default="data/test_repository.db")
#     args = parser.parse_args()

#     workbook_path = Path(args.workbook)
#     tests = sheet_rows(workbook_path, "06_Test_Cases")
#     requirement_to_story = derive_test_story_mapping(workbook_path)

#     missing: list[str] = []
#     normalized: list[dict[str, Any]] = []
#     for row in tests:
#         requirement_id = str(row.get("Requirement_ID") or "").strip()
#         story_id = requirement_to_story.get(requirement_id, "")
#         if not story_id:
#             missing.append(str(row.get("Test_Case_ID")))
#             continue
#         created = row.get("Created_Date")
#         normalized.append({
#             **row,
#             "Story_ID": story_id,
#             "Created_Date": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
#         })

#     if missing:
#         raise SystemExit(f"Tests with no Requirement->Story mapping: {missing[:20]}")

#     repository = TestRepository(args.db)
#     imported = repository.upsert_many(normalized)
#     print(f"Imported/updated {imported} tests. Repository total: {repository.count()}")


# if __name__ == "__main__":
#     main()
