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
from datetime import datetime

import aiosqlite
import crescent
import hikari
import polars as pl
import re2

from bot.constants import (
    CHANNEL_CHOICES,
    complete_channel,
    complete_month,
    database,
    DTD_TYPE_CHOICES,
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
                f"**Fields:** {''.join([f'\nField {i}: \n```\n{value.name}\n{value.value} ```' for i, value in enumerate(embed.fields)])}\n"
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
            "channel_name": pl.String,
            "dtd_type": pl.String,
            "user_id": pl.UInt64,
            "user_name": pl.String,
            "char_name": pl.String,
            "lifestyle": pl.String,
            "remaining_dtd": pl.String,
            "old_purse": pl.Float32,
            "new_purse": pl.Float32,
            "purse_delta": pl.Float32,
            "old_xp": pl.Int32,
            "new_xp": pl.Int32,
            "xp_gained": pl.Int32,
            "old_rpxp": pl.Int32,
            "new_rpxp": pl.Int32,
            "rpxp_delta": pl.Int32,
            "old_rpxp_cache": pl.Int32,
            "new_rpxp_cache": pl.Int32,
            "rpxp_cache_delta": pl.Int32,
            "injuries": pl.String,
            "description": pl.String,
            "message_link": pl.String,
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
    type = crescent.option(
        str, description="(Optional) The type of log you wish to audit.", default="", choices=DTD_TYPE_CHOICES
    )

    async def update_tables(
        self, message_iterator: hikari.LazyIterator[hikari.Message], channel_name: str, channel_id: int, earliest_break: bool = False
    ) -> None:
        message: hikari.Message
        async for message in message_iterator:
            message_id = message.id
            link = cvt.create_discord_url(GUILD_ID, channel_id, message_id)

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
                    logging.debug(f"Issue with description: {link}")
                    continue

                footer = embed.footer.text
                try:
                    if embed.title is None:
                        logging.debug(f"Title not set: {link}")
                        continue
                    if ("Coinpurse" in embed.title) or ("Coin Purse" in embed.title):
                        logging.debug(f"Issue with title: {link}")
                        continue
                    elif "High-Risk Work" in embed.title:
                        to_audit = "hrw"
                    elif footer is None:
                        logging.debug(f"Footer not set: {link}")
                        continue
                    elif "!guild" in footer:
                        to_audit = "guild"
                    elif "!business" in footer:
                        to_audit = "business"
                    elif "!ptw" in footer:
                        to_audit = "ptw"
                    elif "!odd" in footer:
                        to_audit = "odd"
                    elif "train" in footer:
                        to_audit = "train"
                    elif "lifestyle" in footer:
                        to_audit = "lifestyle"
                    elif "transaction" in footer:
                        to_audit = "transactions"
                    elif "dxp" in footer:
                        to_audit = "dxp"
                    elif "rpxp" in footer:
                        to_audit = "rpxp"
                    else:
                        logging.debug(f"Not searchable message: {link}")
                        continue
                except TypeError:
                    logging.debug(f"Message is missing information: {link}")
                    continue
                except Exception as e:
                    logging.debug(e, exc_info=True)
                    logging.debug(link)
                    continue
                if to_audit == "train":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:xp_gained,:message_link,:description,:purse_delta,:old_xp,:new_xp,:channel_name);"""
                elif to_audit == "dxp":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:xp_gained,:description,:message_link,:purse_delta,:old_xp,:new_xp,:channel_name,:old_rpxp,:new_rpxp,:rpxp_delta);"""
                elif to_audit == "rpxp":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:description,:message_link,:purse_delta,:channel_name,:old_rpxp,:new_rpxp,:rpxp_delta,:old_rpxp_cache,:new_rpxp_cache,:rpxp_cache_delta);"""
                elif to_audit == "transactions":
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:description,:message_link,:purse_delta,:channel_name);"""
                else:
                    query = f"""INSERT OR REPLACE INTO {to_audit} VALUES (:message_id,:timestamp,:dtd_remaining,:old_purse,:new_purse,:lifestyle,:injuries,:dtd_type,:user_id,:user_name,:char_name,:message_link,:description,:purse_delta,:channel_name);"""

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
                    char_name = re2.match(r"(.+)gained [\d,]+xp", embed.title)
                if char_name is None:
                    char_name = re2.match(r"Logging [\d\.]+ Hours? RPXP for ([^\!]+)", embed.title)
                if char_name is None:
                    char_name = re2.match(r"Weekly RPXP Cap reset for ([^!]+)", embed.title)
                if char_name is None:
                    char_name = re2.match(r"Character \(Lv\)\n([^\n\r]+)", embed.title)
                if char_name is None:
                    logging.debug(f"Character name not found in {channel_name}: {link}")
                    continue

                xp_gained = None
                old_xp = None
                new_xp = None
                old_rpxp = None
                new_rpxp = None
                rpxp_delta = None
                old_rpxp_cache = None
                new_rpxp_cache = None
                rpxp_cache_delta = None
                output_desc = "N/A"

                match to_audit:
                    case "train":
                        xp_gained = int(re2.search(r"XP Gained:?\*\*:? ([\d,]+)", description)[1].replace(",", ""))
                        try:
                            output_desc = re2.search(r"Note:?\*\*:? ([^\n\r]+)", description)[1]
                        except TypeError:
                            pass
                    case "dxp":
                        old_xp = int(re2.search(r"Change\n([\d,]+)", description)[1].replace(",", ""))
                        new_xp = int(re2.search(r"Change\n(?:[\d,]+) -> ([\d,]+)", description)[1].replace(",", ""))
                        xp_gained = new_xp - old_xp
                        try:
                            old_rpxp = int(re2.search(r"RPXP Transferred\)\n[\d,]+\s\+\s([\d,]+)", description)[1].replace(",", ""))
                        except TypeError:
                            old_rpxp = 0
                        new_rpxp = 0
                        rpxp_delta = new_rpxp - old_rpxp
                        output_desc = re2.search(r"Source\n(.+)", description)[1]
                    case "rpxp":
                        old_rpxp = int(re2.search(r"RPXP\n([\d,]+)", description)[1].replace(",", ""))
                        try:
                            new_rpxp = int(re2.search(r"RPXP\n[\d,]+ -> ([\d,]+)", description)[1].replace(",", ""))
                        except TypeError:
                            new_rpxp = old_rpxp
                        rpxp_delta = new_rpxp - old_rpxp

                        old_rpxp_cache = int(re2.search(r"(?:Cap|reset`|\(Automated\))(\n[\d,]+)", description)[1].replace(",", ""))
                        try:
                            new_rpxp_cache = int(re2.search(r"(?:Cap|reset`|\(Automated\))\n[\d,]+ / [\d,]+ -> ([\d,]+)", description)[1].replace(",", ""))
                        except TypeError:
                            new_rpxp_cache = old_rpxp_cache
                            old_rpxp_cache -= rpxp_delta
                        rpxp_cache_delta = new_rpxp_cache - old_rpxp_cache

                    case "guild":
                        output_desc = re2.match(r"\w+", footer[7:])[0].replace("assasinate", "assassinate")
                    case "business":
                        output_desc = re2.search(r"Business Category:?\*\*:? ([^\n\r]+)", description)[1]
                    case "ptw":
                        output_desc = re2.search(r"Employer:?\*\*:? ([^\n\r]+)", description)[1]
                    case "odd":
                        output_desc = re2.match(r"\w+", footer[5:])[0]
                    case "lifestyle":
                        try:
                            output_desc = re2.search(r"Notes:?\*\*:?\n([^\n\r]+)", description)[1]
                        except TypeError:
                            pass
                    case "transactions":
                        output_desc = embed.description

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
                            "dtd_type": to_audit,
                            "user_id": 0 if user_id_and_name is None else user_id_and_name[1],
                            "user_name": "Unknown" if user_id_and_name is None else user_id_and_name[2],
                            "char_name": char_name[1].strip(),
                            "xp_gained": xp_gained,
                            "description": output_desc,
                            "message_link": link,
                            "purse_delta": 0 if ((old_purse is None) or (new_purse is None)) else (float(new_purse[1]) - float(old_purse[1])),
                            "old_xp": old_xp,
                            "new_xp": new_xp,
                            "channel_name": channel_name,
                            "old_rpxp": old_rpxp,
                            "new_rpxp": new_rpxp,
                            "rpxp_delta": rpxp_delta,
                            "old_rpxp_cache": old_rpxp_cache,
                            "new_rpxp_cache": new_rpxp_cache,
                            "rpxp_cache_delta": rpxp_cache_delta,
                        },
                    )
                    await database.connection.commit()
                except aiosqlite.IntegrityError:
                    logging.debug(f"Value already exists: {link}")
                    continue
                except Exception as e:
                    logging.debug(e, exc_info=True)
                    raise ParsingError(e, GUILD_ID, message.channel_id, message.id)

            # Handles if message does not have an Embed or if Embed doesn't have a Footer
            except (IndexError, AttributeError) as e:
                logging.debug(e, exc_info=True)
                logging.debug(link)
                pass
            except TypeError as e:
                logging.debug(e, exc_info=True)
                raise ParsingError(e, GUILD_ID, message.channel_id, message.id)

    async def filter_tables(self, aware_date: datetime) -> pl.DataFrame:
        filtered_options_list = list(filter(None, map(str.strip, [self.type, str(self.user_id), self.char_name])))
        num_options = len(filtered_options_list)
        match num_options:
            case 0:
                query = """SELECT raw_appended.message_id,
                                  raw_appended.message_timestamp,
                                  raw_appended.channel_name,
                                  raw_appended.dtd_type,
                                  raw_appended.user_id,
                                  raw_appended.user_name,
                                  raw_appended.char_name,
                                  raw_appended.lifestyle,
                                  raw_appended.remaining_dtd,
                                  raw_appended.old_purse,
                                  raw_appended.new_purse,
                                  raw_appended.purse_delta,
                                  raw_appended.old_xp,
                                  raw_appended.new_xp,
                                  raw_appended.xp_gained,
                                  raw_appended.old_rpxp,
                                  raw_appended.new_rpxp,
                                  raw_appended.rpxp_delta,
                                  raw_appended.old_rpxp_cache,
                                  raw_appended.new_rpxp_cache,
                                  raw_appended.rpxp_cache_delta,
                                  raw_appended.injuries,
                                  raw_appended.description,
                                  raw_appended.message_link
                           from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
            case 1:
                query = """SELECT raw_appended.message_id,
                                  raw_appended.message_timestamp,
                                  raw_appended.channel_name,
                                  raw_appended.dtd_type,
                                  raw_appended.user_id,
                                  raw_appended.user_name,
                                  raw_appended.char_name,
                                  raw_appended.lifestyle,
                                  raw_appended.remaining_dtd,
                                  raw_appended.old_purse,
                                  raw_appended.new_purse,
                                  raw_appended.purse_delta,
                                  raw_appended.old_xp,
                                  raw_appended.new_xp,
                                  raw_appended.xp_gained,
                                  raw_appended.old_rpxp,
                                  raw_appended.new_rpxp,
                                  raw_appended.rpxp_delta,
                                  raw_appended.old_rpxp_cache,
                                  raw_appended.new_rpxp_cache,
                                  raw_appended.rpxp_cache_delta,
                                  raw_appended.injuries,
                                  raw_appended.description,
                                  raw_appended.message_link
                           from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE filtered_all MATCH :search_1 AND raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
            case 2:
                query = """SELECT raw_appended.message_id,
                                  raw_appended.message_timestamp,
                                  raw_appended.channel_name,
                                  raw_appended.dtd_type,
                                  raw_appended.user_id,
                                  raw_appended.user_name,
                                  raw_appended.char_name,
                                  raw_appended.lifestyle,
                                  raw_appended.remaining_dtd,
                                  raw_appended.old_purse,
                                  raw_appended.new_purse,
                                  raw_appended.purse_delta,
                                  raw_appended.old_xp,
                                  raw_appended.new_xp,
                                  raw_appended.xp_gained,
                                  raw_appended.old_rpxp,
                                  raw_appended.new_rpxp,
                                  raw_appended.rpxp_delta,
                                  raw_appended.old_rpxp_cache,
                                  raw_appended.new_rpxp_cache,
                                  raw_appended.rpxp_cache_delta,
                                  raw_appended.injuries,
                                  raw_appended.description,
                                  raw_appended.message_link
                           from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE filtered_all MATCH :search_1 AND filtered_all MATCH :search_2 AND raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
            case 3:
                query = """SELECT raw_appended.message_id,
                                  raw_appended.message_timestamp,
                                  raw_appended.channel_name,
                                  raw_appended.dtd_type,
                                  raw_appended.user_id,
                                  raw_appended.user_name,
                                  raw_appended.char_name,
                                  raw_appended.lifestyle,
                                  raw_appended.remaining_dtd,
                                  raw_appended.old_purse,
                                  raw_appended.new_purse,
                                  raw_appended.purse_delta,
                                  raw_appended.old_xp,
                                  raw_appended.new_xp,
                                  raw_appended.xp_gained,
                                  raw_appended.old_rpxp,
                                  raw_appended.new_rpxp,
                                  raw_appended.rpxp_delta,
                                  raw_appended.old_rpxp_cache,
                                  raw_appended.new_rpxp_cache,
                                  raw_appended.rpxp_cache_delta,
                                  raw_appended.injuries,
                                  raw_appended.description,
                                  raw_appended.message_link 
                           from raw_appended INNER JOIN filtered_all ON raw_appended.message_id = filtered_all.rowid WHERE filtered_all MATCH :search_1 AND filtered_all MATCH :search_2 AND filtered_all MATCH :search_3 AND raw_appended.message_timestamp > :timestamp ORDER BY message_timestamp"""
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
            schema_overrides=self.schema,
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
            await self.update_tables(message_iterator, channel_name, channel_id,True)
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
            await self.update_tables(message_iterator, channel_name, channel_id)

        await cursor.close()

        # Fetch all messages stored in database

        sql_df = await self.filter_tables(aware_date)

        time_column = sql_df.select(
            pl.from_epoch("message_timestamp", time_unit="s")
            .dt.convert_time_zone("America/New_York")
            .dt.strftime("%B %d, %Y at %I:%M:%S %p %Z")
            .cast(pl.String)
        ).to_series(0)
        sql_df = sql_df.cast({"old_purse": pl.Decimal(scale=2), "new_purse": pl.Decimal(scale=2), "purse_delta": pl.Decimal(scale=2)})
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
