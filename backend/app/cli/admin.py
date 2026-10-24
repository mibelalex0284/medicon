import argparse
import logging
import sys
import uuid
from typing import Optional

from app.db.session import SessionLocal
from app.models.hospital import Hospital
from app.models.profile import Profile, UserRole

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("admin_cli")


def create_admin_user(
    email: str,
    full_name: str,
    auth_user_id: Optional[str] = None,
    hospital_id: Optional[str] = None,
    phone: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Securely creates an authoritative initial administrator Profile in the database.
    
    SAFETY CONSTRAINTS:
    - Never automatically promotes registered users to admin.
    - Transactionally verifies uniqueness of email and auth identity.
    - Preserves multi-hospital tenant boundaries or configures global super-admin if hospital_id is omitted.
    - Does not expose secrets or passwords.
    """
    clean_email = email.strip().lower()
    clean_name = full_name.strip()
    effective_auth_id = (auth_user_id.strip() if auth_user_id else str(uuid.uuid4()))

    if not clean_email or "@" not in clean_email:
        logger.error("A valid email address is required.")
        return False

    if not clean_name:
        logger.error("A valid full name is required.")
        return False

    db = SessionLocal()
    try:
        # 1. Check for duplicate email across profiles
        existing_email = db.query(Profile).filter(Profile.email == clean_email).first()
        if existing_email:
            logger.error(
                f"A profile with email '{clean_email}' already exists (role={existing_email.role.value})."
            )
            return False

        # 2. Check for duplicate auth user ID
        existing_auth = (
            db.query(Profile).filter(Profile.auth_user_id == effective_auth_id).first()
        )
        if existing_auth:
            logger.error(
                f"A profile linked to auth user ID '{effective_auth_id}' already exists."
            )
            return False

        # 3. Verify hospital ID if specified
        if hospital_id:
            hosp = db.query(Hospital).filter(Hospital.id == hospital_id.strip()).first()
            if not hosp:
                logger.error(f"Hospital with ID '{hospital_id}' does not exist.")
                return False

        if dry_run:
            logger.info("[DRY-RUN] Verification successful. No database records were written.")
            logger.info(
                f"[DRY-RUN] Plan: Profile(email='{clean_email}', name='{clean_name}', "
                f"role='{UserRole.ADMIN.value}', hospital_id='{hospital_id}')"
            )
            return True

        admin_profile = Profile(
            auth_user_id=effective_auth_id,
            role=UserRole.ADMIN,
            full_name=clean_name,
            email=clean_email,
            phone=phone.strip() if phone else None,
            hospital_id=hospital_id.strip() if hospital_id else None,
            is_active=True,
        )
        db.add(admin_profile)
        db.commit()
        db.refresh(admin_profile)

        logger.info("Successfully provisioned initial administrator profile:")
        logger.info(f"  Profile ID   : {admin_profile.id}")
        logger.info(f"  Auth User ID : {admin_profile.auth_user_id}")
        logger.info(f"  Full Name    : {admin_profile.full_name}")
        logger.info(f"  Email        : {admin_profile.email}")
        logger.info(f"  Role         : {admin_profile.role.value}")
        logger.info(
            f"  Hospital ID  : {admin_profile.hospital_id or 'Global Super-Admin (All Hospitals)'}"
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to provision administrator profile: {str(e)}")
        return False
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="CareRoute-X Initial Administrator Bootstrap CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-admin sub-command
    create_parser = subparsers.add_parser(
        "create-admin",
        help="Securely bootstrap an initial administrator account in the local database.",
    )
    create_parser.add_argument(
        "--email",
        required=True,
        help="Email address of the administrator",
    )
    create_parser.add_argument(
        "--full-name",
        required=True,
        help="Full legal name of the administrator",
    )
    create_parser.add_argument(
        "--auth-user-id",
        required=False,
        default=None,
        help="Supabase Auth User UUID (if already created in Supabase Auth). Generates UUID if omitted.",
    )
    create_parser.add_argument(
        "--hospital-id",
        required=False,
        default=None,
        help="Optional hospital ID to bind administrator. Omit for global super-admin.",
    )
    create_parser.add_argument(
        "--phone",
        required=False,
        default=None,
        help="Optional phone number",
    )
    create_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate parameters and prerequisites without making changes to the database.",
    )

    args = parser.parse_args()

    if args.command == "create-admin":
        success = create_admin_user(
            email=args.email,
            full_name=args.full_name,
            auth_user_id=args.auth_user_id,
            hospital_id=args.hospital_id,
            phone=args.phone,
            dry_run=args.dry_run,
        )
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
