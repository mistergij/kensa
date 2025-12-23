"""Defines various conversion functions for the bot.
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

import io
from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl
import xlsxwriter


def to_int(value: str) -> str | int:
    if not value:
        return value
    return int(value)


def convert_day(value: int) -> str:
    return f"{value:02d}"


def convert_date(raw_string: str) -> datetime:
    """Convert the raw date strings to EST/EDT datetime objects.

    Arguments:
      after_raw -- The date in the string format YYYY-MM-DD.

    Returns:
      A time-aware datetime object representing the date.
    """
    try:
        time = datetime.strptime(
            raw_string,
            "%Y-%m-%d",
        ).replace(tzinfo=ZoneInfo("America/New_York"))
    except ValueError:
        time = datetime.strptime(raw_string, "%Y-%B-%d")
    return time


def convert_epoch(epoch: float) -> datetime:
    """Convert the raw date in UNIX Epoch to EST/EDT datetime objects.

    Arguments:
      epoch -- The UNIX epoch time to convert.

    Returns:
      A time-aware datetime object representing the corresponding UNIX epoch time.
    """
    return datetime.fromtimestamp(epoch).replace(tzinfo=ZoneInfo("America/New_York"))


def convert_single_quote_sql(text: str) -> str:
    return str.replace(text, "'", "''").rstrip()


def convert_datetime_to_readable(time: datetime) -> str:
    return time.strftime("%B %d, %Y at %I:%M %p")


def convert_readable_to_epoch(time: str) -> datetime:
    return datetime.strptime(time, "%B %d, %Y at %I:%M %p").replace(tzinfo=ZoneInfo("America/New_York"))


def create_discord_url(guild_id: int, channel_id: int, message_id: int):
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def convert_database_for_output(dataframe: pl.DataFrame) -> pl.DataFrame:
    return dataframe.with_columns(
        [
            pl.col("message_id").cast(pl.Utf8),
            pl.from_epoch("message_timestamp", time_unit="s")
            .dt.convert_time_zone("America/New_York")
            .dt.strftime("%B %d, %Y at %I:%M:%S %p %Z")
            .cast(pl.Utf8),
            pl.col("user_id").cast(pl.Utf8),
            pl.col("old_purse").cast(pl.Decimal(16, 2)),
            pl.col("new_purse").cast(pl.Decimal(16, 2)),
            pl.col("purse_delta").cast(pl.Decimal(16, 2)),
        ]
    )

def write_dataframe_to_excel(dataframe: pl.DataFrame) -> io.BytesIO:
    output_buffer = io.BytesIO()

    with xlsxwriter.Workbook(output_buffer, {"strings_to_urls": False}) as workbook:
        dataframe.write_excel(
            workbook=workbook,
            worksheet="Sheet1",
            position=(0, 0),
            float_precision=2,
        )

    return output_buffer
