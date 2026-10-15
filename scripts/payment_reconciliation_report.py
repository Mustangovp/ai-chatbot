"""Read-only payment reconciliation inventory; never grants/revokes/refunds.

Run in an authorized database environment. Compare flagged purchase references
with Stripe's verified records before any separate, reviewed correction.
"""
import json
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=200)
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error('--limit must be positive')
    print(json.dumps(db.payment_reconciliation_report(arguments.limit), indent=2))
