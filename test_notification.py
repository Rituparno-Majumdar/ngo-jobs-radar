"""
Quick test to verify Telegram credentials and send a sample alert.
Run: python test_notification.py
"""
import os
from dotenv import load_dotenv
from notifier import TelegramNotifier

load_dotenv()

def test_connection():
    notifier = TelegramNotifier()

    # Sample job matching Rituparno's profile
    sample_job = {
        "id": "test_001",
        "title": "Project Coordinator – Community Development",
        "company": "Tata Trusts",
        "url": "https://www.linkedin.com/jobs/view/test",
        "source": "LinkedIn",
        "description": (
            "Seeking an experienced project coordinator to lead community development "
            "initiatives in Jharkhand. MSW preferred. CSR experience a strong advantage."
        ),
        "location": "Jamshedpur, Jharkhand, India"
    }

    print("Sending test alert to Telegram...")
    success = notifier.send_job_alert(sample_job)

    if success:
        print("✅ Test alert sent successfully!")
    else:
        print("❌ Failed to send test alert. Check your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")

    # Also test summary
    print("\nSending summary message...")
    notifier.send_summary(total_new=3, total_checked=47)
    print("✅ Summary sent!")

if __name__ == "__main__":
    test_connection()
