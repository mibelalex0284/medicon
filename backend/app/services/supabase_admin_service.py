import logging
import uuid
from typing import Any, Dict, Optional, Tuple
import httpx
from app.core.config import settings

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

        if not self.is_configured:
            generated_id = str(uuid.uuid4())
            mock_link = f"http://localhost:3000/auth/reset-password?token=mock-invite-{generated_id}"
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
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(generate_link_url, headers=headers, json=invite_payload)
                if res.status_code in (200, 201):
                    data = res.json()
                    auth_user_id = data.get("id") or str(uuid.uuid4())
                    action_link = data.get("action_link")
                    logger.info(f"Successfully generated Supabase Auth invitation link for {email_clean}")
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
                    }
                    rec_res = client.post(generate_link_url, headers=headers, json=recovery_payload)
                    recovery_link = None
                    if rec_res.status_code in (200, 201):
                        rec_data = rec_res.json()
                        recovery_link = rec_data.get("action_link")
                        if not existing_user_id:
                            existing_user_id = rec_data.get("id")

                    final_id = existing_user_id or str(uuid.uuid4())
                    return (
                        final_id,
                        True,
                        recovery_link,
                        "Existing Supabase Auth account linked. Password-setup link generated.",
                        False,
                    )
                else:
                    logger.warning(f"Supabase Auth generate_link returned status {res.status_code}: {res.text}")
                    return (
                        str(uuid.uuid4()),
                        False,
                        None,
                        f"Supabase Auth identity provisioning returned code {res.status_code}.",
                        True,
                    )
        except Exception as e:
            logger.error(f"Error communicating with Supabase Auth admin endpoint: {type(e).__name__}")
            return (
                str(uuid.uuid4()),
                False,
                None,
                "Local profile created. Remote identity provisioning encountered a network error.",
                True,
            )

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
