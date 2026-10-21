"""Bounded subprocess execution for local read-only and admin tools."""

import asyncio
from collections.abc import Sequence

from ..tool_result import ToolResult


class OutputLimitError(Exception):
    """A command exceeded the configured combined output limit."""


async def run_command(
    argv: Sequence[str],
    *,
    timeout: int,
    max_output_bytes: int,
) -> ToolResult:
    """Execute fixed argv without a shell, bounding memory and elapsed time.

    stdout and stderr are consumed concurrently to prevent pipe deadlocks.
    On timeout or output overflow the process is terminated before returning.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return ToolResult(
            success=False,
            error={"code": "NOT_INSTALLED", "message": f"Missing executable: {argv[0]}"},
        )
    except OSError as exc:
        return ToolResult(
            success=False,
            error={"code": "OS_ERROR", "message": str(exc)},
        )

    size = 0

    async def drain(stream: asyncio.StreamReader) -> bytes:
        nonlocal size
        chunks = []
        while chunk := await stream.read(8192):
            size += len(chunk)
            if size > max_output_bytes:
                raise OutputLimitError
            chunks.append(chunk)
        return b"".join(chunks)

    tasks = [
        asyncio.create_task(drain(process.stdout)),
        asyncio.create_task(drain(process.stderr)),
        asyncio.create_task(process.wait()),
    ]
    try:
        async with asyncio.timeout(timeout):
            stdout, stderr, exit_code = await asyncio.gather(*tasks)
    except (TimeoutError, OutputLimitError) as exc:
        if process.returncode is None:
            process.kill()
        await process.wait()
        code = "TIMEOUT" if isinstance(exc, TimeoutError) else "OUTPUT_LIMIT"
        return ToolResult(
            success=False,
            error={"code": code, "message": "Command time/output limit exceeded"},
        )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    data = {
        "exit_code": exit_code,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
    if exit_code != 0:
        return ToolResult(
            success=False,
            data=data,
            error={"code": "COMMAND_FAILED", "message": f"{argv[0]} exited {exit_code}"},
        )
    return ToolResult(success=True, data=data)
