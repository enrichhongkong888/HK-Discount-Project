# -*- coding: utf-8 -*-
"""After-fill remediation report comparing empty-store mall counts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from audit_empty_store_malls import main as run_audit  # noqa: E402

OUT = ROOT / "data" / "cache" / "empty_store_remediation_report.md"
BEFORE = ROOT / "data" / "cache" / "empty_store_audit_before.json"


def snapshot() -> dict:
    run_audit()
    return json.loads((ROOT / "data" / "cache" / "empty_store_audit.json").read_text(encoding="utf-8"))


def main() -> int:
    before = None
    if BEFORE.exists():
        before = json.loads(BEFORE.read_text(encoding="utf-8"))
    after = snapshot()
    after_empty = {r["mall_name"] for r in after.get("empty_malls") or []}
    lines = ["# Empty-store remediation report", ""]
    if before:
        before_empty = {r["mall_name"] for r in before.get("empty_malls") or []}
        filled = sorted(before_empty - after_empty)
        still = sorted(before_empty & after_empty)
        lines.extend(
            [
                f"- Before empty malls: **{len(before_empty)}**",
                f"- After empty malls: **{len(after_empty)}**",
                f"- Newly filled: **{len(filled)}**",
                f"- Still empty: **{len(still)}**",
                "",
                "## Newly filled",
                "",
            ]
        )
        for name in filled:
            lines.append(f"- {name}")
        lines.extend(["", "## Still empty", ""])
        for name in still:
            lines.append(f"- {name}")
    else:
        lines.append(f"- Current empty malls: **{len(after_empty)}**")
        for name in sorted(after_empty):
            lines.append(f"- {name}")
    s = after.get("summary") or {}
    lines.extend(
        [
            "",
            "## SPA coverage",
            "",
            f"- Total malls: {s.get('total_malls')}",
            f"- With store offers: {s.get('malls_with_store_offers')}",
            f"- Empty store offers: {s.get('malls_empty_store_offers')}",
            "",
        ]
    )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
