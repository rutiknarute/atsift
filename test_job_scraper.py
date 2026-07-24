import csv
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import job_scraper


class JobScraperTests(unittest.TestCase):
    def test_is_recent_accepts_naive_iso_timestamp(self) -> None:
        timestamp = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(minutes=5)
        ).isoformat()

        self.assertTrue(job_scraper.is_recent(timestamp, 1))

    def test_empty_run_clears_stale_csv_results(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "new_jobs.csv"
            seen_ids_path = Path(temporary_directory) / "seen_ids.json"
            output_path.write_text("stale result\n", encoding="utf-8")

            with (
                patch.object(job_scraper, "OUTPUT_FILE", str(output_path)),
                patch.object(job_scraper, "SEEN_IDS_FILE", str(seen_ids_path)),
                patch.object(job_scraper, "load_companies", return_value=[]),
            ):
                job_scraper.main()

            with output_path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

            self.assertEqual([], rows)
            self.assertEqual([], json.loads(seen_ids_path.read_text()))


if __name__ == "__main__":
    unittest.main()
