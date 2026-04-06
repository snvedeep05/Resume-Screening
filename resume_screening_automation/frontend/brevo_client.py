import re
import streamlit as st
import brevo_python
from brevo_python.rest import ApiException
from datetime import datetime


class BrevoClient:

    def __init__(self):
        self.api_key = st.secrets["BREVO_API_KEY"]
        self.default_sender_email = st.secrets["BREVO_SENDER_EMAIL"]
        self.default_sender_name = st.secrets.get("BREVO_SENDER_NAME", "AppWeave Labs")

        configuration = brevo_python.Configuration()
        configuration.api_key["api-key"] = self.api_key
        self.api_client = brevo_python.ApiClient(configuration)
        self.email_api = brevo_python.TransactionalEmailsApi(self.api_client)

    def send_template_email(self, to_email, template_id, params, to_name=None):
        try:
            recipient = {"email": to_email}
            if to_name:
                recipient["name"] = to_name

            email_data = brevo_python.SendSmtpEmail(
                to=[recipient],
                template_id=template_id,
                params=params or {},
                sender={
                    "email": self.default_sender_email,
                    "name": self.default_sender_name,
                }
            )

            response = self.email_api.send_transac_email(email_data)
            print(f"✅ Sent to {to_email} — Message ID: {response.message_id}")
            return True

        except ApiException as e:
            print(f"❌ Brevo API error for {to_email}: {e}")
            return False

    def get_templates(self) -> list:
        """Fetch all templates from Brevo. Returns list of {id, name, is_active}."""
        try:
            response = self.email_api.get_smtp_templates(limit=50, offset=0)
            return [
                {
                    "id":        t.id,
                    "name":      t.name,
                    "is_active": getattr(t, "is_active", True),
                }
                for t in (response.templates or [])
            ]
        except ApiException as e:
            print(f"[Brevo] get_templates failed: {e}")
            return []

    def get_template_params(self, template_id: int) -> list:
        """
        Fetch template HTML and extract unique {{params.X}} placeholders.
        Handles Brevo syntax including defaults: {{ params.FIRSTNAME | default : "Applicant" }}
        Returns list of param names in order of appearance, deduplicated.
        """
        try:
            template = self.email_api.get_smtp_template(template_id)
            html = (template.html_content or "") + (template.subject or "")
            # Match {{ params.PARAMNAME ... }} with optional default/filter syntax
            matches = re.findall(r'\{\{-?\s*params\.(\w+)\s*(?:\|[^}]*)?\}\}', html)
            seen = {}
            for m in matches:
                seen[m] = None  # preserve order, deduplicate
            return list(seen.keys())
        except ApiException as e:
            print(f"[Brevo] get_template_params failed: {e}")
            return []

    def get_daily_stats(self) -> dict:
        remaining = 300
        try:
            account_api = brevo_python.AccountApi(self.api_client)
            account     = account_api.get_account()
            plans       = account.plan or []
            send_plan   = next((p for p in plans if p.credits_type == "sendLimit" and p.type != "sms"), None)
            if send_plan:
                remaining = int(send_plan.credits or 300)
        except Exception as e:
            print(f"[Brevo] AccountApi failed: {e}")

        used = max(300 - remaining, 0)

        # SMTP stats for delivered/bounced
        today = datetime.today().strftime("%Y-%m-%d")
        try:
            report       = self.email_api.get_aggregated_smtp_report(start_date=today, end_date=today)
            delivered    = report.delivered    or 0
            hard_bounces = report.hard_bounces or 0
            soft_bounces = report.soft_bounces or 0
        except Exception as e:
            print(f"[Brevo] SMTP stats failed: {e}")
            delivered = hard_bounces = soft_bounces = 0

        return {
            "requests":     used,
            "delivered":    delivered,
            "hard_bounces": hard_bounces,
            "soft_bounces": soft_bounces,
        }
