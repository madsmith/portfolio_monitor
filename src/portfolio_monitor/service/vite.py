import asyncio
from pathlib import Path


class ViteProcess:
    def __init__(self, process: asyncio.subprocess.Process, host: str, port: int, frontend_dir: Path) -> None:
        self.process: asyncio.subprocess.Process = process
        self.host: str = host
        self.port: int = port
        self.frontend_dir: Path = frontend_dir

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    def terminate(self) -> None:
        self.process.terminate()

    async def wait(self) -> int:
        return await self.process.wait()


async def start_vite(frontend_dir: Path, host: str = "127.0.0.1", port: int = 5174) -> ViteProcess:
    process = await asyncio.create_subprocess_exec(
        "pnpm", "dev", "--port", str(port), cwd=str(frontend_dir)
    )
    return ViteProcess(process=process, host=host, port=port, frontend_dir=frontend_dir)
