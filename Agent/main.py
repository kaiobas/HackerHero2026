"""
HackerHero Guardian – Ponto de Entrada

Inicia o servidor FastAPI + o orquestrador em background.

Uso:
    python main.py

Ou diretamente via uvicorn:
    uvicorn main:app --host 127.0.0.1 --port 8000
"""

import asyncio
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import router
from app.guardian import GuardianOrchestrator
from config import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
)
logger.add(
    "logs/guardian_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="DEBUG",
    encoding="utf-8",
)

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

async def _install_ollama() -> bool:
    """
    Tenta instalar o Ollama automaticamente conforme o sistema operacional:
      - macOS  : brew install ollama  (fallback: curl do script oficial)
      - Linux  : curl -fsSL https://ollama.com/install.sh | sh
      - Windows: baixa e executa o installer .exe silenciosamente
    Retorna True se a instalação foi bem-sucedida.
    """
    import platform
    import subprocess
    import shutil
    import tempfile
    import urllib.request

    plat = platform.system()
    logger.info("🔧 Instalando Ollama automaticamente ({})...", plat)

    try:
        if plat == "Darwin":
            # Tenta Homebrew primeiro
            if shutil.which("brew"):
                logger.info("Usando Homebrew para instalar Ollama...")
                proc = await asyncio.create_subprocess_exec(
                    "brew", "install", "ollama",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    logger.success("✅ Ollama instalado via Homebrew.")
                    return True
                logger.warning("Homebrew falhou ({}). Tentando script oficial...",
                               stdout.decode(errors="replace").strip()[-200:])

            # Fallback: script oficial (mesmo que Linux)
            script_url = "https://ollama.com/install.sh"
            logger.info("Baixando script de instalação em {}...", script_url)
            proc = await asyncio.create_subprocess_shell(
                f"curl -fsSL {script_url} | sh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await proc.communicate()
            return proc.returncode == 0

        elif plat == "Linux":
            proc = await asyncio.create_subprocess_shell(
                "curl -fsSL https://ollama.com/install.sh | sh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await proc.communicate()
            if proc.returncode == 0:
                logger.success("✅ Ollama instalado via script oficial.")
                return True
            logger.error("Falha na instalação do Ollama (Linux).")
            return False

        elif plat == "Windows":
            installer_url = "https://ollama.com/download/OllamaSetup.exe"
            tmp = tempfile.mktemp(suffix=".exe")
            logger.info("Baixando instalador Windows de {}...", installer_url)

            def _download():
                urllib.request.urlretrieve(installer_url, tmp)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _download)

            proc = await asyncio.create_subprocess_exec(
                tmp, "/S",   # /S = instalação silenciosa (NSIS)
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode == 0:
                logger.success("✅ Ollama instalado no Windows.")
                return True
            logger.error("Falha ao instalar Ollama no Windows (código {}).", proc.returncode)
            return False

        else:
            logger.error("Sistema operacional '{}' não suportado para auto-install.", plat)
            return False

    except Exception as exc:
        logger.error("Erro durante auto-install do Ollama: {}", exc)
        return False


async def _ensure_ollama() -> None:
    """Garante que o Ollama está rodando e o modelo está disponível."""
    import subprocess
    import httpx
    import shutil

    ollama_url = settings.ollama_url
    model = settings.ollama_model

    # 1. Instala automaticamente se o binário não existir
    if not shutil.which("ollama"):
        logger.warning("Ollama não está instalado — iniciando instalação automática...")
        ok = await _install_ollama()
        if not ok:
            logger.error(
                "❌ Não foi possível instalar o Ollama automaticamente. "
                "Instale manualmente em: https://ollama.com/download"
            )
            return
        # Pequena pausa para o sistema registrar o novo binário
        await asyncio.sleep(2)

    # 2. Inicia o serviço se ainda não estiver rodando
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            await c.get(f"{ollama_url}/api/tags")
        logger.info("✅ Ollama já está rodando em {}", ollama_url)
    except Exception:
        logger.info("Iniciando serviço Ollama...")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Aguarda até 10s o serviço subir
        for _ in range(10):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient(timeout=2) as c:
                    await c.get(f"{ollama_url}/api/tags")
                logger.success("✅ Serviço Ollama iniciado.")
                break
            except Exception:
                continue
        else:
            logger.error("❌ Ollama não respondeu após 10s. Verifique manualmente.")
            return

    # 3. Verifica se o modelo está disponível
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            resp = await c.get(f"{ollama_url}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
        if not any(model in m for m in models):
            logger.warning("Modelo '{}' não encontrado — baixando (pode demorar)...", model)
            proc = await asyncio.create_subprocess_exec(
                "ollama", "pull", model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await proc.wait()
            logger.success("✅ Modelo '{}' pronto.", model)
        else:
            logger.info("✅ Modelo '{}' disponível.", model)
    except Exception as exc:
        logger.error("Erro ao verificar modelo Ollama: {}", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    await _ensure_ollama()

    guardian = GuardianOrchestrator()
    app.state.guardian = guardian
    await guardian.start()
    logger.success("✅ {} v{} rodando em http://{}:{}",
                   settings.app_name, settings.app_version,
                   settings.api_host, settings.api_port)
    yield
    # ── Shutdown ──
    await guardian.stop()
    logger.info("Servidor encerrado.")


# ---------------------------------------------------------------------------
# Aplicação FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API de proteção de crianças em jogos online. "
        "Monitora a tela, detecta padrões suspeitos e aciona proteção em tempo real."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ---------------------------------------------------------------------------
# Health-check simples (sem autenticação)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok", "app": settings.app_name}


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="warning",   # uvicorn silencioso – loguru cuida do resto
    )
