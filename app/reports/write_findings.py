"""Write output/findings.json for one analysis: python -m app.reports.write_findings <id>."""

import json
import sys
from contextlib import closing
from pathlib import Path

from app.analyses import service as analyses
from app.config import settings
from app.db import connect
from app.reports.service import build_content

OUTPUT_PATH = Path("output") / "findings.json"


def main(analysis_id: str) -> None:
    with closing(connect(settings.database_path)) as conn:
        analysis = analyses.get_analysis(conn, analysis_id)
        content = build_content(conn, analysis)
    # Filled in by hand at submission from the time log.
    content["active_time_minutes"] = None
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT_PATH} for {analysis_id} ({analysis.status})")  # noqa: T201


if __name__ == "__main__":
    main(sys.argv[1])
