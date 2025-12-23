"""Defines a database class for variable storage.
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

from dataclasses import dataclass, field
import io

import aiosqlite
import polars as pl
from sqlalchemy import Engine


@dataclass
class Database:
    """Class to keep track of Kensa's SQLite databases"""

    connection: aiosqlite.Connection = None
    earliest_audit: float = None
    engine: Engine = None
    file: io.TextIOBase = None
    schema: dict[str, pl.Any] = field(
        default_factory=lambda: {
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
    )
