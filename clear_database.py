#!/usr/bin/env python3
"""
Script to clear the database from test data.

"""

import asyncio
from sqlalchemy import delete

from app.db.session import sessionmanager
from app.core.config import settings
from app.models.meeting_models import (
    Meeting,
    Transcription,
    MeetingTopic,
    Decision,
    ActionItem,
)
from app.models.user import User, APIToken


async def clear_all_data():
    """Remove all data from the database."""
    print("WARNING: This will delete ALL data from the database.")
    print(f"Database URL: {settings.DATABASE_URL}")

    response = input("Are you sure? Type 'yes' to continue: ")
    if response.lower() != "yes":
        print("Cancelled.")
        return

    print("Clearing database...")

    async with sessionmanager.session() as db:
        try:
            #  dependent tables first
            print("Deleting action items...")
            await db.execute(delete(ActionItem))

            print("Deleting decisions...")
            await db.execute(delete(Decision))

            print("Deleting topics...")
            await db.execute(delete(MeetingTopic))

            print("Deleting transcriptions...")
            await db.execute(delete(Transcription))

            print("Deleting meetings...")
            await db.execute(delete(Meeting))

            print("Deleting API tokens...")
            await db.execute(delete(APIToken))

            print("Deleting users...")
            await db.execute(delete(User))

            await db.commit()
            print("Database cleared successfully.")

        except Exception as e:
            await db.rollback()
            print(f"Failed to clear database: {e}")
            import traceback
            traceback.print_exc()
            raise


async def clear_only_meetings():
    """Remove meeting-related data only"""
    print("WARNING: This will delete ALL meetings")
    print("Users will NOT be deleted")

    response = input("Are you sure? Type 'yes' to continue: ")
    if response.lower() != "yes":
        print("Cancelled.")
        return

    print("Clearing meetings...")

    async with sessionmanager.session() as db:
        try:
            print("Deleting action items...")
            await db.execute(delete(ActionItem))

            print("Deleting decisions...")
            await db.execute(delete(Decision))

            print("Deleting topics...")
            await db.execute(delete(MeetingTopic))

            print("Deleting transcriptions...")
            await db.execute(delete(Transcription))

            print("Deleting meetings...")
            await db.execute(delete(Meeting))

            await db.commit()
            print("Meetings deleted successfully.")

        except Exception as e:
            await db.rollback()
            print(f"Failed to clear meetings: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--meetings-only":
        asyncio.run(clear_only_meetings())
    else:
        asyncio.run(clear_all_data())
