"""Doctor Schedule Repair Utility.

Safe, idempotent administrative script to inspect and initialize default schedules
for active doctors who currently lack configured consultation hours.

Usage:
    # Dry run preview (no database modifications)
    python backend/scripts/repair_doctor_schedules.py --dry-run

    # Execute repair across all hospitals
    python backend/scripts/repair_doctor_schedules.py

    # Repair a specific doctor
    python backend/scripts/repair_doctor_schedules.py --doctor-id <doctor_id>

    # Repair doctors in a specific hospital
    python backend/scripts/repair_doctor_schedules.py --hospital-id <hospital_id>
"""

import argparse
import sys
from pathlib import Path

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.session import SessionLocal
from app.services.doctor_service import doctor_service


def main():
    parser = argparse.ArgumentParser(
        description="Idempotent repair utility for unscheduled doctors in CareRoute-X."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the repair without committing any database modifications.",
    )
    parser.add_argument(
        "--doctor-id",
        type=str,
        default=None,
        help="Optional specific doctor ID to inspect and repair.",
    )
    parser.add_argument(
        "--hospital-id",
        type=str,
        default=None,
        help="Optional specific hospital ID to filter doctors by.",
    )

    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 60)
        print("CareRoute-X Doctor Schedule Repair Utility")
        print("=" * 60)
        mode_str = "DRY-RUN (No changes will be written)" if args.dry_run else "LIVE REPAIR (Changes will be committed)"
        print(f"Mode: {mode_str}")
        if args.doctor_id:
            print(f"Doctor Target: {args.doctor_id}")
        if args.hospital_id:
            print(f"Hospital Target: {args.hospital_id}")
        print("-" * 60)

        if args.doctor_id:
            # Single doctor mode
            doc = doctor_service.get_doctor(db, args.doctor_id)
            prof_name = doc.profile.full_name if doc.profile else "Unknown"
            print(f"Inspecting doctor '{prof_name}' ({doc.id})...")
            from app.repositories.doctor_schedule_repository import doctor_schedule_repo
            existing = doctor_schedule_repo.get_by_doctor(db, doctor_id=doc.id, is_active=True)
            if existing:
                print(f"Doctor already has {len(existing)} active schedule window(s). Preserving existing schedules. No action needed.")
            else:
                print(f"Doctor currently has 0 active schedules.")
                if args.dry_run:
                    print(f"[DRY-RUN] Would create 5 default weekday schedules (Mon-Fri 09:00 - 17:00, 30 min slots).")
                else:
                    schedules = doctor_service.create_default_schedules(db, doctor_id=doc.id, overwrite=False)
                    db.commit()
                    print(f"Successfully initialized {len(schedules)} default schedule window(s) for Dr. {prof_name}.")
        else:
            # Bulk repair mode
            result = doctor_service.repair_unscheduled_doctors(
                db, hospital_id=args.hospital_id, dry_run=args.dry_run
            )
            print(f"Unscheduled doctors identified: {result['unscheduled_count']}")
            for d in result["doctors"]:
                doc_name = d.get("doctor_name", "Unknown")
                doc_id = d.get("doctor_id")
                if args.dry_run:
                    print(f"  - [Needs Schedule] Dr. {doc_name} ({doc_id})")
                else:
                    count = d.get("schedules_created", 0)
                    print(f"  - [Repaired] Dr. {doc_name} ({doc_id}): {count} schedule windows created.")

            if args.dry_run:
                print("-" * 60)
                print(f"Dry-run complete. Run without --dry-run to commit default schedules.")
            else:
                print("-" * 60)
                print(f"Repair complete. {result['repaired_count']} doctor(s) repaired successfully.")
        print("=" * 60)
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Repair utility failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
