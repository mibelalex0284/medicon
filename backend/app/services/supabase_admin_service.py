import logging
import uuid
from typing import Any, Dict, Optional, Tuple
import httpx
from app.core.config import settings
from app.core.exceptions import ConflictError

logger = logging.getLogger(__name__)


class SupabaseAdminService:
    """Manages administrative Supabase Auth operations using the backend service-role key.

    CRITICAL SECURITY RULES:
    1. The SUPABASE_SERVICE_ROLE_KEY is used exclusively on the FastAPI backend.
    2. Credentials and tokens are NEVER exposed to client responses or logs.
    3. Gracefully handles unconfigured dev environments, network timeouts, and duplicate accounts.
    """

    @property
    def is_configured(self) -> bool:
        return bool(
            settings.SUPABASE_URL
            and "placeholder" not in settings.SUPABASE_URL
            and "your-project" not in settings.SUPABASE_URL
            and settings.SUPABASE_SERVICE_ROLE_KEY
            and "placeholder" not in settings.SUPABASE_SERVICE_ROLE_KEY
            and "your-supabase-service-role-key" not in settings.SUPABASE_SERVICE_ROLE_KEY
        )

    def _get_headers(self) -> Dict[str, str]:
        return {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY or "",
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY or ''}",
            "Content-Type": "application/json",
        }

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Queries Supabase Auth to check if a user already exists by email."""
        if not self.is_configured:
            return None

        email_clean = email.strip().lower()
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=self._get_headers(), params={"page": 1, "per_page": 50})
                if res.status_code == 200:
                    users = res.json().get("users", [])
                    for u in users:
                        if (u.get("email") or "").strip().lower() == email_clean:
                            return u
        except Exception as e:
            logger.error(f"Error querying Supabase Auth user by email: {type(e).__name__}")
        return None
    def get_all_users_map(self) -> Dict[str, Dict[str, Any]]:
        """Queries Supabase Auth and returns a dictionary of email -> user metadata dict."""
        if not self.is_configured:
            return {}
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
        try:
            with httpx.Client(timeout=6.0) as client:
                res = client.get(url, headers=self._get_headers(), params={"page": 1, "per_page": 100})
                if res.status_code == 200:
                    users = res.json().get("users", [])
                    return {
                        (u.get("email") or "").strip().lower(): u
                        for u in users
                        if u.get("email")
                    }
        except Exception as e:
            logger.error(f"Error querying Supabase Auth users map: {type(e).__name__}")
        return {}

    def create_doctor_user(
        self,
        email: str,
        password: str,
        full_name: str,
        role: str = "doctor",
    ) -> Tuple[str, bool, str, bool]:
        """Creates an authenticated physician identity directly in Supabase Auth using the provided password.

        Returns:
            Tuple[auth_user_id: str, auth_provisioned: bool, message: str, is_newly_created: bool]
        """
        email_clean = email.strip().lower()

        if not self.is_configured:
            generated_id = str(uuid.uuid4())
            logger.info(f"Supabase service-role key not configured. Mock identity provisioned for development: {email_clean}.")
            return (
                generated_id,
                False,
                "Physician onboarded successfully (development mock identity).",
                True,
            )

        # 1. Explicitly check if user identity already exists in Supabase Auth
        existing_user = self.get_user_by_email(email_clean)
        if existing_user:
            metadata_role = (existing_user.get("user_metadata") or {}).get("role")
            if metadata_role in ("patient", "admin"):
                raise ConflictError(
                    message=f"An account with email '{email_clean}' already exists in Supabase Auth with role '{metadata_role}'. Existing accounts cannot be promoted to physician.",
                    code="CANNOT_PROMOTE_EXISTING_ROLE",
                )
            raise ConflictError(
                message=f"An account with email '{email_clean}' already exists in Supabase Auth. Existing user accounts cannot be overwritten with a new password during onboarding.",
                code="AUTH_USER_ALREADY_EXISTS",
            )

        # 2. Call backend-only Supabase Admin API: POST /auth/v1/admin/users
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
        headers = self._get_headers()
        create_payload = {
            "email": email_clean,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": full_name,
                "role": role,
            },
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, headers=headers, json=create_payload)
                if res.status_code in (200, 201):
                    data = res.json()
                    auth_user_id = data.get("id") or (data.get("user") or {}).get("id")
                    if not auth_user_id:
                        raise RuntimeError(
                            f"Supabase Auth created user for '{email_clean}', but did not return a valid Auth UUID."
                        )
                    logger.info(f"Successfully created Supabase Auth account for {email_clean} (UUID: {auth_user_id})")
                    return (
                        auth_user_id,
                        True,
                        "Physician account provisioned successfully in Supabase Auth.",
                        True,
                    )
                elif res.status_code == 422 or "already" in res.text.lower() or "exists" in res.text.lower():
                    logger.warning(f"User {email_clean} already exists in Supabase Auth.")
                    raise ConflictError(
                        message=f"An account with email '{email_clean}' already exists in Supabase Auth. Existing user accounts cannot be overwritten with a new password during onboarding.",
                        code="AUTH_USER_ALREADY_EXISTS",
                    )
                else:
                    logger.warning(f"Supabase Auth admin create user returned status {res.status_code}")
                    raise RuntimeError(
                        f"Supabase Auth identity provisioning returned code {res.status_code}: {res.text}"
                    )
        except ConflictError:
            raise
        except Exception as e:
            logger.error(f"Error communicating with Supabase Auth admin create user endpoint: {type(e).__name__} - {str(e)}")
            raise

    def invite_or_provision_doctor(
        self,
        email: str,
        full_name: str,
        role: str = "doctor",
    ) -> Tuple[str, bool, Optional[str], str, bool]:
        """Provisions or invites a doctor identity in Supabase Auth.

        Returns:
            Tuple[auth_user_id: str, auth_provisioned: bool, action_link: Optional[str], message: str, is_newly_created: bool]
        """
        email_clean = email.strip().lower()
        redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/account-setup?mode=set-password"

        if not self.is_configured:
            generated_id = str(uuid.uuid4())
            mock_link = f"{settings.FRONTEND_URL.rstrip('/')}/account-setup?mode=set-password&token=mock-invite-{generated_id}"
            logger.info(f"Supabase service-role key not configured. Mock invite link generated for {email_clean}.")
            return (
                generated_id,
                False,
                mock_link,
                "Local profile created. Invitation link generated for development environment.",
                True,
            )

        generate_link_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/generate_link"
        headers = self._get_headers()

        # Attempt 1: Generate invite link (creates user if not already present)
        invite_payload = {
            "type": "invite",
            "email": email_clean,
            "data": {
                "full_name": full_name,
                "role": role,
            },
            "redirect_to": redirect_url,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(generate_link_url, headers=headers, json=invite_payload)
                if res.status_code in (200, 201):
                    data = res.json()
                    auth_user_id = data.get("id") or (data.get("user") or {}).get("id")
                    if not auth_user_id:
                        existing_u = self.get_user_by_email(email_clean)
                        auth_user_id = existing_u.get("id") if existing_u else None
                    if not auth_user_id:
                        raise RuntimeError(
                            f"Supabase Auth generated invite link for '{email_clean}', but did not return a valid Auth UUID."
                        )
                    action_link = data.get("action_link")
                    logger.info(f"Successfully generated Supabase Auth invitation link for {email_clean} (UUID: {auth_user_id})")
                    return (
                        auth_user_id,
                        True,
                        action_link,
                        "Physician onboarded successfully and invitation generated.",
                        True,
                    )
                elif res.status_code == 422 or "already" in res.text.lower() or "exists" in res.text.lower():
                    # User already exists in Supabase Auth
                    logger.info(f"User {email_clean} already exists in Supabase Auth; generating password setup recovery link.")
                    # Query existing user ID
                    existing_user = self.get_user_by_email(email_clean)
                    existing_user_id = existing_user.get("id") if existing_user else None

                    # Generate recovery link for password setup
                    recovery_payload = {
                        "type": "recovery",
                        "email": email_clean,
                        "redirect_to": redirect_url,
                    }
                    rec_res = client.post(generate_link_url, headers=headers, json=recovery_payload)
                    recovery_link = None
                    if rec_res.status_code in (200, 201):
                        rec_data = rec_res.json()
                        recovery_link = rec_data.get("action_link")
                        if not existing_user_id:
                            existing_user_id = rec_data.get("id") or (rec_data.get("user") or {}).get("id")

                    if not existing_user_id:
                        raise RuntimeError(
                            f"User '{email_clean}' exists in Supabase Auth, but could not resolve their existing Auth user ID. Refusing to generate a random UUID fallback."
                        )

                    return (
                        existing_user_id,
                        True,
                        recovery_link,
                        "Existing Supabase Auth account linked. Password-setup link generated.",
                        False,
                    )
                else:
                    logger.warning(f"Supabase Auth generate_link returned status {res.status_code}: {res.text}")
                    raise RuntimeError(
                        f"Supabase Auth identity provisioning returned code {res.status_code}: {res.text}"
                    )
        except Exception as e:
            logger.error(f"Error communicating with Supabase Auth admin endpoint: {type(e).__name__} - {str(e)}")
            raise

    def resend_or_generate_invitation(
        self,
        email: str,
        full_name: str,
    ) -> Tuple[Optional[str], str, bool]:
        """Regenerates or resends an invitation / password setup link for an existing doctor.

        Returns:
            Tuple[action_link: Optional[str], message: str, auth_provisioned: bool]
        """
        email_clean = email.strip().lower()
        redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/account-setup?mode=set-password"

        if not self.is_configured:
            mock_link = f"{settings.FRONTEND_URL.rstrip('/')}/account-setup?mode=set-password&token=mock-resend-{str(uuid.uuid4())[:8]}"
            logger.info(f"Supabase not configured. Mock resend invite link generated for {email_clean}.")
            return (
                mock_link,
                "Invitation link refreshed for development environment.",
                False,
            )

        generate_link_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/generate_link"
        headers = self._get_headers()

        # Check if user identity already exists in Supabase Auth
        existing_user = self.get_user_by_email(email_clean)

        try:
            with httpx.Client(timeout=10.0) as client:
                if existing_user:
                    # User already exists in Auth: generate recovery link for secure password setup
                    recovery_payload = {
                        "type": "recovery",
                        "email": email_clean,
                        "redirect_to": redirect_url,
                    }
                    res = client.post(generate_link_url, headers=headers, json=recovery_payload)
                    if res.status_code in (200, 201):
                        data = res.json()
                        action_link = data.get("action_link")
                        return (
                            action_link,
                            "Physician invitation / password-setup link regenerated successfully.",
                            True,
                        )
                    else:
                        raise RuntimeError(
                            f"Failed to generate recovery link for existing user: {res.status_code} {res.text}"
                        )
                else:
                    # User does not exist yet: generate invite link
                    invite_payload = {
                        "type": "invite",
                        "email": email_clean,
                        "data": {
                            "full_name": full_name,
                            "role": "doctor",
                        },
                        "redirect_to": redirect_url,
                    }
                    res = client.post(generate_link_url, headers=headers, json=invite_payload)
                    if res.status_code in (200, 201):
                        data = res.json()
                        action_link = data.get("action_link")
                        return (
                            action_link,
                            "Physician identity provisioned and new invitation link generated.",
                            True,
                        )
                    else:
                        raise RuntimeError(
                            f"Failed to generate invitation link: {res.status_code} {res.text}"
                        )
        except Exception as e:
            logger.error(f"Error resending Supabase Auth invitation: {type(e).__name__} - {str(e)}")
            raise

    def provision_user_identity(
        self,
        email: str,
        full_name: str,
        role: str,
    ) -> Tuple[str, bool, str]:
        """Provisions a standard user identity in Supabase Auth (backward compatibility)."""
        auth_id, provisioned, _, message, _ = self.invite_or_provision_doctor(
            email=email, full_name=full_name, role=role
        )
        return auth_id, provisioned, message

    def delete_user(self, auth_user_id: str) -> bool:
        """Deletes an Auth user by ID from Supabase Auth (for rollback or safe deletion)."""
        if not self.is_configured or not auth_user_id:
            return True

        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{auth_user_id}"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.delete(url, headers=self._get_headers())
                if res.status_code in (200, 204, 404):
                    logger.info(f"Supabase Auth user {auth_user_id} deleted successfully.")
                    return True
                logger.warning(f"Failed to delete Supabase Auth user {auth_user_id}: {res.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error deleting Supabase Auth user {auth_user_id}: {type(e).__name__}")
            return False


supabase_admin_service = SupabaseAdminService()
