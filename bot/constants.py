"""Defines various constants for the bot.
Copyright © 2025 Dnd World

This file is part of Kensa.
Kensa is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any
later version.

Kensa is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
details.

You should have received a copy of the GNU General Public License along with Kensa. If not, see
<https://www.gnu.org/licenses/>.
"""

import datetime
import os
from collections.abc import Sequence

import crescent
import hikari
from dotenv import find_dotenv, load_dotenv

from bot.database import Database


load_dotenv(find_dotenv(usecwd=True))

Plugin = crescent.Plugin[hikari.GatewayBot, None]

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
if DISCORD_TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable is not set.")

AVRAE_ID = os.environ.get("AVRAE_ID")
if AVRAE_ID is None:
    raise ValueError("AVRAE_ID environment variable is not set.")

GUILD_ID = os.environ.get("GUILD_ID")
if GUILD_ID is None:
    raise ValueError("GUILD_ID environment variable is not set.")

DEV_IDS = os.environ.get("DEV_IDS")
if DEV_IDS is None:
    raise ValueError("DEV_IDS environment variable is not set.")
DEV_IDS = DEV_IDS.split(",")

DISCORD_URL = "https://discord.com/channels/"

MAIN_DATABASE_PATH = os.path.join(os.getcwd(), "resources", "database.sqlite")
GUILD_DATABASE_PATH = os.path.join(os.getcwd(), "resources", "guild.sqlite")
EARLIEST_AUDIT_PATH = os.path.join(os.getcwd(), "resources", "earliest_audit.txt")
DTD_TYPE_CHOICES = [
    ("business", "business"),
    ("dxp", "dxp"),
    ("guild", "guild"),
    ("hrw", "hrw"),
    ("lifestyle","lifestyle"),
    ("odd", "odd"),
    ("ptw", "ptw"),
    ("rpxp", "rpxp"),
    ("train", "train"),
    ("transactions", "transactions"),
]

MONTH_CHOICES = [
    ("January", "01"),
    ("February", "02"),
    ("March", "03"),
    ("April", "04"),
    ("May", "05"),
    ("June", "06"),
    ("July", "07"),
    ("August", "08"),
    ("September", "09"),
    ("October", "10"),
    ("November", "11"),
    ("December", "12"),
]


async def complete_month(
    ctx: crescent.AutocompleteContext, option: hikari.AutocompleteInteractionOption
) -> Sequence[tuple[str, str]]:
    return MONTH_CHOICES


DAY_DICTIONARY = {
    "01": 31,
    "02": 28,
    "03": 31,
    "04": 30,
    "05": 31,
    "06": 30,
    "07": 31,
    "08": 31,
    "09": 30,
    "10": 31,
    "11": 30,
    "12": 31,
}

CHANNEL_CHOICES = [
    ("dtd-automated-log", "579777361117970465"),
    ("lifestyle-log", "586471153141284866"),
    ("transaction-log", "531011819095982081"),
    ("xp-tracker", "531014104098537481"),
]


async def complete_channel(
    ctx: crescent.AutocompleteContext, option: hikari.AutocompleteInteractionOption
) -> Sequence[tuple[str, str]]:
    return CHANNEL_CHOICES


ERROR_LOG_PATH = os.path.normpath(os.path.join(os.getcwd(), "logs", f"{datetime.datetime.now()}.log"))

CHANNEL_LIST = []

database = Database()
