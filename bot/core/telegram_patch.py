"""
Monkey-patch kurigram's save_file to use larger chunk sizes for
high-bandwidth servers. Must be applied BEFORE client.start().
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Union, BinaryIO, Callable

from pyrogram import Client, raw

from bot import LOGGER

# Configurable chunk sizes (bytes)
UPLOAD_CHUNK_SIZE = 1024 * 1024     # 1MB (default was 512KB)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024   # 1MB


async def _patched_save_file(
    self: Client,
    path: Union[str, BinaryIO],
    file_id: int = None,
    file_part: int = 0,
    progress: Callable = None,
    progress_args: tuple = ()
):
    """
    Enhanced save_file with configurable chunk size.
    Drop-in replacement for pyrogram.Client.save_file.
    """
    part_size = UPLOAD_CHUNK_SIZE

    if isinstance(path, (str, Path)):
        fp = open(path, "rb")
        file_name = os.path.basename(path)
        file_size = os.path.getsize(path)
        close_after = True
    else:
        fp = path
        file_name = getattr(fp, "name", "upload")
        fp.seek(0, 2)
        file_size = fp.tell()
        fp.seek(0)
        close_after = False

    if file_id is None:
        file_id = int.from_bytes(os.urandom(8), "little", signed=True)

    file_total_parts = math.ceil(file_size / part_size)
    is_big = file_size > 10 * 1024 * 1024  # >10MB uses BigFilePart

    try:
        while True:
            chunk = fp.read(part_size)
            if not chunk:
                break

            if is_big:
                rpc = raw.functions.upload.SaveBigFilePart(
                    file_id=file_id,
                    file_part=file_part,
                    file_total_parts=file_total_parts,
                    bytes=chunk,
                )
            else:
                rpc = raw.functions.upload.SaveFilePart(
                    file_id=file_id,
                    file_part=file_part,
                    bytes=chunk,
                )

            await self.invoke(rpc)

            if progress:
                func = progress(
                    min(file_part * part_size + len(chunk), file_size),
                    file_size,
                    *progress_args,
                )
                if func and callable(getattr(func, "__await__", None)):
                    await func

            file_part += 1
    finally:
        if close_after:
            fp.close()

    if is_big:
        return raw.types.InputFileBig(
            id=file_id,
            parts=file_total_parts,
            name=file_name,
        )
    else:
        return raw.types.InputFile(
            id=file_id,
            parts=file_total_parts,
            name=file_name,
            md5_checksum="",
        )


def apply_patches():
    """Apply all Pyrogram/kurigram performance patches."""
    Client.save_file = _patched_save_file
    LOGGER.info(
        f"Patched kurigram: upload_chunk={UPLOAD_CHUNK_SIZE // 1024}KB, "
        f"download_chunk={DOWNLOAD_CHUNK_SIZE // 1024}KB"
    )
