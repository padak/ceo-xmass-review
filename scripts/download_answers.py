#!/usr/bin/env python3
"""Download all survey answers from Keboola to local data/ folder for debugging."""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from kbcstorage.client import Client

load_dotenv()

# Configuration
KBC_URL = os.environ.get("KBC_URL") or os.environ.get("KBC_API_URL", "https://connection.keboola.com")
KBC_TOKEN = os.environ.get("KBC_TOKEN") or os.environ.get("KBC_API_TOKEN", "")
ANSWERS_TAG = os.environ.get("ANSWERS_TAG", "Christmas_Survey_2025_v1")

DATA_DIR = Path(__file__).parent.parent / "data"


def main():
    if not KBC_TOKEN:
        print("Error: KBC_TOKEN not set")
        sys.exit(1)

    print(f"Connecting to {KBC_URL}")
    print(f"Looking for files with tag: {ANSWERS_TAG}")

    client = Client(KBC_URL, KBC_TOKEN)
    files_client = client.files

    # List all files with the tag
    files_list = files_client.list(tags=[ANSWERS_TAG], limit=1000)
    print(f"Found {len(files_list)} files")

    # Create data directory
    DATA_DIR.mkdir(exist_ok=True)

    all_answers = []

    for file_info in files_list:
        file_id = file_info.get("id")
        file_name = file_info.get("name", "unknown.json")

        # Extract email from tags
        file_tags = file_info.get("tags", [])
        tag_names = [t.get("name") if isinstance(t, dict) else t for t in file_tags]

        user_email = None
        for tag in tag_names:
            if tag != ANSWERS_TAG and "@" in tag:
                user_email = tag
                break

        if not user_email:
            print(f"  Skipping {file_id} - no email tag")
            continue

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                files_client.download(file_id, tmp_dir)
                local_path = os.path.join(tmp_dir, file_name)

                with open(local_path, "r") as f:
                    data = json.load(f)
                    data["_user_email"] = user_email
                    all_answers.append(data)
                    print(f"  Downloaded: {user_email}")

        except Exception as e:
            print(f"  Error downloading {file_id}: {e}")
            continue

    # Save all answers to a single JSON file
    output_file = DATA_DIR / "all_answers.json"
    with open(output_file, "w") as f:
        json.dump(all_answers, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_answers)} answers to {output_file}")

    # Also save individual files for easier inspection
    individual_dir = DATA_DIR / "individual"
    individual_dir.mkdir(exist_ok=True)

    for answer in all_answers:
        email = answer.get("_user_email", "unknown")
        safe_name = email.replace("@", "_at_").replace(".", "_")
        individual_file = individual_dir / f"{safe_name}.json"
        with open(individual_file, "w") as f:
            json.dump(answer, f, indent=2, ensure_ascii=False)

    print(f"Saved individual files to {individual_dir}")


if __name__ == "__main__":
    main()
