"""Plugin that contains all audit commands for the bot.
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
import logging
from collections.abc import Sequence
from datetime import datetime
from urllib.parse import urljoin

import aiosqlite
import crescent
import hikari
import polars as pl
import re2
import sys

from bot.constants import (
    CHANNEL_CHOICES,
    complete_channel,
    complete_month,
    database,
    DISCORD_URL,
    GUILD_DTD_CHOICES,
    GUILD_ID,
    Plugin,
)
from bot.errors import ArgumentError, ParsingError
import bot.converters as cvt

plugin = Plugin()
audit_commands = crescent.Group("audit")


@plugin.include
@crescent.command(description="Ping the bot to check if it's online.")
async def ping(ctx: crescent.Context) -> None:
    """Returns the bot's latency in milliseconds."""
    current_latency = plugin.app.heartbeat_latency
    await ctx.respond(f"Pong!\nLatency: {current_latency * 1000:.2f} ms")


@plugin.include
@audit_commands.child
@crescent.command(name="get_message", description="Performs a new audit of the server's logs.")
class GetMessage:
    channel_id = crescent.option(
        str,
        description="The ID of the message's channel.",
        autocomplete=complete_channel,
    )
    message_id = crescent.option(
        str,
        description="The ID of the message.",
    )
    content_type = crescent.option(
        int, description="The type of content you want to return", choices=[("message", 0), ("embed", 1)]
    )

    async def callback(self, ctx: crescent.Context):
        logging.info("/audit get_message command called.")
        message = await plugin.app.rest.fetch_message(int(self.channel_id), int(self.message_id))
        if self.content_type == 0:
            await ctx.respond(message)
        else:
            embed = message.embeds[0]
            await ctx.respond(
                f"**Title:** `{embed.title}`\n"
                f"**Description:** ```{embed.description}```\n"
                f"**Fields:** {''.join([f'\nField {i}: \n```{value.name}\n{value.value} ```' for i, value in enumerate(embed.fields)])}\n"
                f"**Footer:** `{embed.footer}`\n"
                f"**Timestamp:** `{message.timestamp.timestamp()}`\n"
            )
        logging.info("/audit get_message command finished executing.")


@plugin.include
@audit_commands.child
@crescent.command(
    name="full",
    description="Intelligently fetch and store data from DTDs",
)
class AuditDTDs:
    def __init__(self):
        self.schema = {
            "message_id": pl.UInt64,
            "message_timestamp": pl.Float64,
            "remaining_dtd": pl.UInt8,
            "old_purse": pl.Float32,
            "new_purse": pl.Float32,
            "lifestyle": pl.String,
            "injuries": pl.String,
            "dtd_type": pl.String,
            "user_id": pl.UInt64,
            "user_name": pl.String,
            "char_name": pl.String,
        }

    year = crescent.option(
        str,
        description="The year after which to audit.",
    ).convert(cvt.to_int)
    month = crescent.option(str, description="The month after which to audit.", autocomplete=complete_month)
    day = crescent.option(int, description="The day after which to audit.").convert(cvt.convert_day)
    char_name = crescent.option(str, description="(Optional) The name of the character to audit.", default="")
    user_id = crescent.option(str, description="(Optional) The ID of the User to audit.", default="").convert(
        cvt.to_int
    )
    dtd_type = crescent.option(
        str, description="(Optional) The DTD type you wish to audit.", default="", choices=GUILD_DTD_CHOICES
    )

    async def update_tables(
        self, message_iterator: hikari.LazyIterator[hikari.Message], earliest_break: bool = False
    ) -> None:
        async for message in message_iterator:
            try:
                if (
                    (database.earliest_audit is not None)
                    and (message.timestamp.timestamp() > database.earliest_audit)
                    and earliest_break
                ):
                    logging.debug("Breaking because data is already in tables.")
                    break

                embed = message.embeds[0]
                description = embed.description

                if description is None:
                    description = ""

                for field in embed.fields:
                    description += f"\n{field.name}\n{field.value}"

                if description == "":
                    logging.debug(f"Issue with description: {cvt.to_url(message)}")
                    continue

                footer = embed.footer.text
                try:
                    if embed.title is None:
                        logging.debug(f"Title not set: {cvt.to_url(message)}")
                        continue
                    if ("Coinpurse" in embed.title) or ("Coin Purse" in embed.title):
                        logging.debug(f"Issue with title: {cvt.to_url(message)}")
                        continue
                    elif "High-Risk Work" in embed.title:
                        to_audit = "hrw"
                        dtd_type = "N/A"
                    elif footer is None:
                        logging.debug(f"Footer not set: {cvt.to_url(message)}")
                        continue
                    elif "!guild" in footer:
                        to_audit = "guild"
                        dtd_type = re2.match(r"\w+", footer[7:])[0].replace("assasinate", "assassinate")
                    elif "!business" in footer:
                        to_audit = "business"
                        dtd_type = re2.search(r"Business Category:?\*\*:? ([^\n\r]+)", description)[1]
                    elif "!ptw" in footer:
                        to_audit = "ptw"
                        dtd_type = "Part-Time Work"
                    elif "!odd" in footer:
                        to_audit = "odd"
                        dtd_type = re2.match(r"\w+", footer[5:])[0]
                    elif "train" in footer:
                        to_audit = "train"
                        dtd_type = "Combat Training"
                    elif "lifestyle" in footer:
                        to_audit = "lifestyle"
                        dtd_type = "N/A"
                    elif "transaction" in footer:
                        to_audit = "transactions"
                        dtd_type = "N/A"
                    elif "dxp" in footer:
                        to_audit = "dxp"
                        dtd_type = "N/A"
                    # elif "rpxp" in footer:
                    #     to_audit = "rpxp"
                    #     dtd_type = "N/A"
                    else:
                        logging.debug(f"Not searchable message: {cvt.to_url(message)}")
                        continue
                except TypeError:
                    parts = [GUILD_ID, str(message.channel_id), str(message.id)]
                    logging.debug(f"Message is missing information: {cvt.to_url(message)}")
                    continue
                except Exception as e:
                    logging.debug(e, exc_info=True)
                    continue
                if to_audit == "train":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:xp_gained);"""
                elif to_audit == "dxp":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:xp_gained,:description);"""
                elif to_audit == "rpxp":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:rpxp_gained);"""
                elif to_audit == "transactions":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:description);"""
                else:
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name);"""

                message_id = message.id
                message_timestamp = message.timestamp
                dtd_remaining = description.count("◉")
                is_dtd = True if dtd_remaining > 0 or description.count("〇") > 0 else False
                old_purse = re2.search(r"(\d+\.\d+)gp -> \d+\.\d+gp \(", description)
                new_purse = re2.search(r"-> (\d+\.\d+)", description)
                lifestyle = re2.search(r"Lifestyle:?\*\*:? ([^\n\r]+)", description)
                injuries = re2.search(r"Injuries:?\*\*:? ([^\n\r]+)", description)
                user_id_and_name = re2.search(r"Player:?\*\*:? <@(\d+)> `([^`\n\r]+)", description)
                char_name = re2.search(r"Character:?\*\*:? ([^\n]+)", description)
                if char_name is None:
                    char_name = re2.match(r"(.+)makes a transaction!", embed.title)
                if char_name is None:
                    char_name = re2.match(r"(.+)gained \d,*\d*xp!", embed.title)
                if char_name is None:
                    logging.debug(f"Character name not found: {cvt.to_url(message)}")
                    continue

                xp_gained = None
                output_desc = "N/A"

                if to_audit == "train":
                    xp_gained = int(re2.search(r"XP Gained:?\*\*:? (\d+)", description)[1])
                    output_desc = embed.description
                elif to_audit == "dxp":
                    xp_old = re2.search(r"XP Change\n(\d+,*\d*)", description)[1].replace(",", "")
                    xp_new = re2.search(r"XP Change\n\d+,*\d* -> (\d+,*\d*)", description)[1].replace(",", "")
                    xp_gained = int(xp_new) - int(xp_old)
                    output_desc = re2.search(r"Source\n(.+)", description)[1]

                try:
                    await database.connection.execute(
                        query,
                        {
                            "message_id": message_id,
                            "timestamp": message_timestamp.timestamp(),
                            "dtd_remaining": dtd_remaining if is_dtd else -1,
                            "old_purse": 0 if old_purse is None else float(old_purse[1]),
                            "new_purse": 0 if new_purse is None else float(new_purse[1]),
                            "lifestyle": "Unknown" if lifestyle is None else lifestyle[1],
                            "injuries": "None" if injuries is None else injuries[1],
                            "dtd_type": dtd_type,
                            "user_id": 0 if user_id_and_name is None else user_id_and_name[1],
                            "user_name": "Unknown" if user_id_and_name is None else user_id_and_name[2],
                            "char_name": char_name[1].strip(),
                            "xp_gained": xp_gained,
                            "description": output_desc,
                        },
                    )
                    await database.connection.commit()
                except aiosqlite.IntegrityError:
                    logging.debug(f"Value already exists: {cvt.to_url(message)}")
                    continue
                except TypeError as e:
                    raise ParsingError(e, GUILD_ID, message.channel_id, message.id)

            # Handles if message does not have an Embed or if Embed doesn't have a Footer
            except (IndexError, AttributeError):
                pass
            except TypeError as e:
                raise ParsingError(e, GUILD_ID, message.channel_id, message.id)

    async def filter_tables(self, aware_date: datetime) -> pl.DataFrame:
        filtered_options_list = list(filter(None, map(str.strip, [self.dtd_type, str(self.user_id), self.char_name])))
        num_options = len(filtered_options_list)
        match num_options:
            case 0:
                query = """SELECT raw_appended.* from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
            case 1:
                query = """SELECT raw_appended.* from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE filtered_all MATCH :search_1 AND raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
            case 2:
                query = """SELECT raw_appended.* from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE filtered_all MATCH :search_1 AND filtered_all MATCH :search_2 AND raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
            case 3:
                query = """SELECT raw_appended.* from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE filtered_all MATCH :search_1 AND filtered_all MATCH :search_2 AND filtered_all MATCH :search_3 AND raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
            case _:
                raise ArgumentError(filtered_options_list)

        return pl.read_database(
            query,
            database.engine,
            execute_options={
                "parameters": {
                    "timestamp": aware_date.timestamp(),
                    "search_1": f'"{filtered_options_list[0]}"' if num_options > 0 else None,
                    "search_2": f'"{filtered_options_list[1]}"' if num_options > 1 else None,
                    "search_3": f'"{filtered_options_list[2]}"' if num_options > 2 else None,
                }
            },
        )

    async def callback(self, ctx: crescent.Context) -> None:
        logging.info("/audit full command called.")
        await ctx.respond("Audit started. This may take a few minutes. Please wait...")
        aware_date = cvt.convert_date(f"{self.year}-{self.month}-{self.day}")
        for channel_name, channel_id in CHANNEL_CHOICES:
            logging.debug(f"Fetching messages from channel: {channel_name}")
            message_iterator: hikari.LazyIterator[hikari.Message] = plugin.app.rest.fetch_messages(
                int(channel_id), after=aware_date
            )

            # Find messages not yet in database
            await self.update_tables(message_iterator, True)
            logging.debug(f"Fetched messages from channel: {channel_name}")

        # Update variables to reflect new entries in database
        try:
            database.earliest_audit = min(aware_date.timestamp(), database.earliest_audit)
        except TypeError:
            database.earliest_audit = aware_date.timestamp()
        logging.debug("Updated earliest audit")

        # Create cursor to find most recent timestamp in database
        cursor = await database.connection.execute(
            "SELECT message_timestamp FROM raw_all ORDER BY message_timestamp DESC LIMIT 1"
        )
        latest_sql_timestamp = await cursor.fetchone()
        for channel_name, channel_id in CHANNEL_CHOICES:
            message_iterator: hikari.LazyIterator[hikari.Message] = plugin.app.rest.fetch_messages(
                int(channel_id),
                after=cvt.convert_epoch(float(latest_sql_timestamp[0])),
            )

            # Find messages sent after SQL Database was last updated
            await self.update_tables(message_iterator)

        await cursor.close()

        # Fetch all messages stored in database

        sql_df = await self.filter_tables(aware_date)

        time_column = sql_df.select(
            pl.from_epoch("message_timestamp", time_unit="s")
            .dt.convert_time_zone("America/New_York")
            .cast(pl.String)
            .replace("T", "")
        ).to_series(0)
        sql_df.replace_column(1, time_column)
        output_string = sql_df.write_csv()
        output_file = io.StringIO(output_string)
        await ctx.respond(
            attachment=hikari.Bytes(
                output_file,
                "audit.csv",
                "text/csv",
            )
        )
        logging.info(f"/audit full finished executing.")


@plugin.include
@crescent.catch_command(ArgumentError)
async def catch_argument_error(exc: ArgumentError, ctx: crescent.Context) -> None:
    await ctx.respond(exc)


@plugin.include
@crescent.catch_command(ParsingError)
async def catch_parsing_error(exc: ParsingError, ctx: crescent.Context) -> None:
    await ctx.respond(f"Unexpected error! Please provide the following information to <@657638997941813258>:\n{exc}")
