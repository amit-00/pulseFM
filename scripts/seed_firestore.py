"""
Seed Firestore with the documents required for PulseFM to start up.

Usage:
    python scripts/seed_firestore.py

Requires:
    - google-cloud-firestore
    - GOOGLE_CLOUD_PROJECT env var (or Application Default Credentials configured)
"""

import argparse
from datetime import datetime, timedelta, timezone

from google.cloud.firestore import Client


STUBBED_VOTE_ID = "stubbed"
STUBBED_DURATION_MS = 150_000  # 2.5 minutes — default loop duration


def seed(project_id: str | None = None, dry_run: bool = False):
    db = Client(project=project_id)
    now = datetime.now(timezone.utc)

    # ── 1. stations/main ────────────────────────────────────────────────
    stations_main = {
        "voteId": STUBBED_VOTE_ID,
        "startAt": now,
        "endAt": now + timedelta(milliseconds=STUBBED_DURATION_MS),
        "durationMs": STUBBED_DURATION_MS,
        "next": {
            "voteId": STUBBED_VOTE_ID,
            "duration": STUBBED_DURATION_MS,
        },
    }

    # ── 2. songs/stubbed ────────────────────────────────────────────────
    songs_stubbed = {
        "voteId": STUBBED_VOTE_ID,
        "durationMs": STUBBED_DURATION_MS,
    }

    # ── 3. heartbeat/main ───────────────────────────────────────────────
    heartbeat_main = {
        "active_listeners": 1,
    }

    docs = [
        ("stations", "main", stations_main),
        ("songs", "stubbed", songs_stubbed),
        ("heartbeat", "main", heartbeat_main),
    ]

    for collection, doc_id, data in docs:
        ref = db.collection(collection).document(doc_id)
        if dry_run:
            print(f"[DRY RUN] Would write {collection}/{doc_id}:")
            for k, v in data.items():
                print(f"  {k}: {v}")
        else:
            ref.set(data, merge=True)
            print(f"✅ Seeded {collection}/{doc_id}")

    if not dry_run:
        print("\nAll documents seeded. System is ready to start.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Firestore for PulseFM startup")
    parser.add_argument("--project", default=None, help="GCP project ID (uses ADC default if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without writing")
    parser.add_argument("--duration-ms", type=int, default=STUBBED_DURATION_MS, help="Stubbed song duration in ms (default: 150000)")
    args = parser.parse_args()

    STUBBED_DURATION_MS = args.duration_ms
    seed(project_id=args.project, dry_run=args.dry_run)

