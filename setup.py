"""
╔═══════════════════════════════════════════════════════════════╗
║  🟣 RALLY AGENT — Package Setup                              ║
║  pip install .            → core only                        ║
║  pip install .[all]       → everything                       ║
║  pip install .[voice]     → voice features                   ║
║  pip install .[browser]   → browser automation               ║
║  pip install .[rag]       → vector memory & RAG              ║
║  pip install .[dev]       → development tools                ║
╚═══════════════════════════════════════════════════════════════╝
"""

from setuptools import setup, find_packages
from pathlib import Path

here = Path(__file__).parent

# Read long description from README
long_description = ""
readme = here / "README.md"
if readme.exists():
    long_description = readme.read_text(encoding="utf-8")

# Read version from core/version.py
version = "2.0.0"
version_file = here / "core" / "version.py"
if version_file.exists():
    for line in version_file.read_text().splitlines():
        if line.startswith("__version__"):
            version = line.split("=")[1].strip().strip('"').strip("'")
            break

setup(
    name="rally-agent",
    version=version,
    description="The OpenClaw Killer — Your AI. Your Rules. Your Data.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Rally Labs",
    url="https://github.com/Atum246/rally-agent",
    project_urls={
        "Homepage": "https://github.com/Atum246/rally-agent",
        "Documentation": "https://github.com/Atum246/rally-agent#readme",
        "Repository": "https://github.com/Atum246/rally-agent",
        "Issues": "https://github.com/Atum246/rally-agent/issues",
    },
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(exclude=["tests", "tests.*", "docs", "docs.*"]),
    include_package_data=True,
    package_data={
        "": ["*.toml", "*.yaml", "*.yml", "*.json", "*.txt", "*.md"],
    },
    entry_points={
        "console_scripts": [
            "rally=rally:main",
        ],
    },
    install_requires=[
        "httpx>=0.27.0",
        "rich>=13.7.0",
        "prompt-toolkit>=3.0.43",
        "pyyaml>=6.0.1",
        "fastapi>=0.110.0",
        "uvicorn>=0.29.0",
        "websockets>=12.0",
        "cryptography>=42.0.0",
    ],
    extras_require={
        # ── Browser automation ─────────────────────────────────
        "browser": [
            "playwright>=1.42.0",
            "beautifulsoup4>=4.12.3",
        ],
        # ── Voice features ─────────────────────────────────────
        "voice": [
            "edge-tts>=6.1.9",
        ],
        "voice-full": [
            "edge-tts>=6.1.9",
            "openai-whisper>=20231117",
            "TTS>=0.22.0",
            "openwakeword>=0.6.0",
        ],
        # ── RAG & Vector memory ────────────────────────────────
        "rag": [
            "chromadb>=0.4.22",
            "sentence-transformers>=2.5.1",
        ],
        # ── Document processing ────────────────────────────────
        "docs": [
            "beautifulsoup4>=4.12.3",
            "markdown>=3.5.2",
            "PyPDF2>=3.0.1",
            "pdfplumber>=0.11.0",
            "python-docx>=1.1.0",
        ],
        # ── Data & Analysis ────────────────────────────────────
        "data": [
            "numpy>=1.26.4",
            "pandas>=2.2.0",
        ],
        # ── Database support ───────────────────────────────────
        "db": [
            "psycopg2-binary>=2.9.9",
            "redis>=5.0.1",
        ],
        # ── Image processing ───────────────────────────────────
        "image": [
            "Pillow>=10.2.0",
            "reportlab>=4.1.0",
        ],
        # ── Fine-tuning ────────────────────────────────────────
        "finetune": [
            "datasets>=2.18.0",
            "transformers>=4.38.2",
            "torch>=2.2.0",
            "peft>=0.10.0",
            "trl>=0.8.1",
            "bitsandbytes>=0.43.0",
        ],
        # ── Everything ─────────────────────────────────────────
        "all": [
            "playwright>=1.42.0",
            "beautifulsoup4>=4.12.3",
            "markdown>=3.5.2",
            "edge-tts>=6.1.9",
            "numpy>=1.26.4",
        ],
        # ── Development ────────────────────────────────────────
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0",
            "pytest-cov>=4.1.0",
            "black>=24.1.0",
            "ruff>=0.2.0",
            "mypy>=1.8.0",
            "isort>=5.13.0",
            "pre-commit>=3.6.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Communications :: Chat",
    ],
    keywords=[
        "ai", "agent", "cli", "llm", "openclaw", "chat",
        "voice", "browser", "rag", "plugins", "self-hosted",
    ],
)
