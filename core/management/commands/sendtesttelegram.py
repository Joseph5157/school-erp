"""Send one fixed test message to the operator's Telegram crash-alert chat.

Run from the production service shell after setting TELEGRAM_ERROR_BOT_TOKEN and
TELEGRAM_ERROR_CHAT_ID (docs/OPERATIONS.md). The message holds no request, student,
guardian or account data. It uses the same transport as crash alerts but skips their
five-minute cooldown. Output is one short line; the token, chat ID and Telegram address are
never printed. Exits non-zero when the message is not delivered.
"""

from django.core.management.base import BaseCommand, CommandError

from config import telegram_alerts


class Command(BaseCommand):
    help = "Send one fixed test message to the Telegram crash-alert chat."

    def handle(self, *args, **options):
        if not telegram_alerts.alerts_configured():
            raise CommandError(
                "Telegram crash alerts are not configured. Set TELEGRAM_ERROR_BOT_TOKEN and "
                "TELEGRAM_ERROR_CHAT_ID on the production service; debug and test runs "
                "always keep the alerts off."
            )
        if not telegram_alerts.send_message(telegram_alerts.test_message_text()):
            raise CommandError(
                "The Telegram test alert could not be delivered. Check the bot token, the chat "
                "ID and that the operator has sent /start to the bot, then try again."
            )
        self.stdout.write("Telegram test alert sent.")
