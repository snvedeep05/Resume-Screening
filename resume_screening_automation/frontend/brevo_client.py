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

    def get_daily_stats(self) -> dict:
        today = datetime.today().strftime("%Y-%m-%d")
        try:
            report = self.email_api.get_aggregated_smtp_report(
                start_date=today,
                end_date=today
            )
            return {
                "requests":     report.requests     or 0,
                "delivered":    report.delivered    or 0,
                "hard_bounces": report.hard_bounces or 0,
                "soft_bounces": report.soft_bounces or 0,
                "blocked":      report.blocked      or 0,
            }
        except Exception as e:
            print(f"Failed to fetch Brevo daily stats: {e}")
            return {
                "requests": 0, "delivered": 0,
                "hard_bounces": 0, "soft_bounces": 0, "blocked": 0
            }
