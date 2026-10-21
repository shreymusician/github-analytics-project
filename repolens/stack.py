"""Stack detection from facts (manifests, extensions, config), not from guessing."""
from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from pathlib import Path

from .files import iter_files, read_text

LANG_BY_EXT = {
    ".py": "Python", ".ipynb": "Jupyter", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".kt": "Kotlin", ".c": "C", ".h": "C", ".cpp": "C++", ".cs": "C#", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".r": "R", ".sql": "SQL", ".sh": "Shell",
    ".html": "HTML", ".css": "CSS", ".vue": "Vue", ".svelte": "Svelte",
}

# dependency name -> capability tags. This hand-built taxonomy is the project's
# domain knowledge; extend it as new AI/ML libraries appear.
TAXONOMY: dict[str, list[str]] = {
    "torch": ["deep-learning", "pytorch"], "tensorflow": ["deep-learning", "tensorflow"],
    "keras": ["deep-learning"], "jax": ["deep-learning"], "transformers": ["nlp", "huggingface"],
    "sklearn": ["classical-ml"], "scikit-learn": ["classical-ml"], "xgboost": ["classical-ml"],
    "lightgbm": ["classical-ml"], "pandas": ["data"], "numpy": ["data"],
    "langchain": ["llm-orchestration"], "langgraph": ["llm-orchestration", "agents"],
    "llama-index": ["llm-orchestration", "rag"], "llama_index": ["llm-orchestration", "rag"],
    "openai": ["llm-api"], "anthropic": ["llm-api"], "ollama": ["local-llm"],
    "chromadb": ["vector-db", "rag"], "faiss-cpu": ["vector-db", "rag"], "faiss": ["vector-db"],
    "pinecone": ["vector-db"], "qdrant-client": ["vector-db"], "weaviate-client": ["vector-db"],
    "sentence-transformers": ["embeddings", "rag"], "opencv-python": ["computer-vision"],
    "cv2": ["computer-vision"], "ultralytics": ["computer-vision", "yolo"],
    "fastapi": ["web-api"], "flask": ["web-api"], "django": ["web-framework"],
    "streamlit": ["web-ui", "demo-app"], "gradio": ["web-ui", "demo-app"],
    "react": ["frontend"], "next": ["frontend"], "vue": ["frontend"], "express": ["web-api"],
    "sqlalchemy": ["database"], "psycopg2": ["database"], "pymongo": ["database"],
    "redis": ["cache"], "celery": ["task-queue"], "docker": ["containers"],
    "pytest": ["testing"], "jest": ["testing"], "mlflow": ["mlops"], "wandb": ["mlops"],
    "dvc": ["mlops"], "pillow": ["imaging"], "moviepy": ["video"], "matplotlib": ["visualization"],
    "plotly": ["visualization"], "scipy": ["scientific"], "requests": ["http-client"],
    "httpx": ["http-client"], "beautifulsoup4": ["scraping"], "selenium": ["scraping"],
    "scrapy": ["scraping"], "pydantic": ["data-validation"], "pytorch-lightning": ["deep-learning"],
    "diffusers": ["generative-ai"], "gym": ["reinforcement-learning"], "gymnasium": ["reinforcement-learning"],
    "stable-baselines3": ["reinforcement-learning"], "spacy": ["nlp"], "nltk": ["nlp"],
    "onnxruntime": ["inference"], "tensorrt": ["inference"], "vllm": ["inference", "llm-serving"],
}

_REQ = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*(==|>=|<=|~=|>|<|!=)?\s*([^\s;#]*)")


TAXONOMY = {k.replace("_", "-"): v for k, v in TAXONOMY.items()}


def _canon(name: str) -> str:
    return name.lower().replace("_", "-")


def _parse_requirements(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", "git+", "http")):
            continue
        m = _REQ.match(line)
        if m:
            out[_canon(m.group(1))] = (m.group(2) or "") + (m.group(3) or "")
    return out


def _parse_pyproject(text: str) -> dict[str, str]:
    try:
        d = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    deps = list(d.get("project", {}).get("dependencies", []))
    out = _parse_requirements("\n".join(deps))
    for k, v in d.get("tool", {}).get("poetry", {}).get("dependencies", {}).items():
        if k.lower() != "python":
            out[_canon(k)] = v if isinstance(v, str) else ""
    return out


def _parse_package_json(text: str) -> dict[str, str]:
    try:
        d = json.loads(text)
    except ValueError:
        return {}
    out = {}
    for sec in ("dependencies", "devDependencies"):
        sec_d = d.get(sec)
        if isinstance(sec_d, dict):
            out.update({_canon(k): str(v) for k, v in sec_d.items()})
    return out


def _parse_go_mod(text: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in re.finditer(r"^\s*(?:require\s+)?([\w./\-]+)\s+(v[\w.\-+]+)", text, re.M)}


def _parse_cargo(text: str) -> dict[str, str]:
    try:
        d = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    return {k.lower(): (v if isinstance(v, str) else str(v.get("version", "")) if isinstance(v, dict) else "")
            for k, v in d.get("dependencies", {}).items()}


MANIFESTS = {
    "requirements.txt": _parse_requirements, "pyproject.toml": _parse_pyproject,
    "package.json": _parse_package_json, "go.mod": _parse_go_mod, "cargo.toml": _parse_cargo,
}
LOCKFILES = {"poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "pipfile.lock",
             "uv.lock", "cargo.lock", "go.sum"}


CATEGORY_BY_EXT = {
    **{e: "code" for e in LANG_BY_EXT if e not in (".ipynb", ".html", ".css")},
    ".ipynb": "notebooks", ".html": "web", ".css": "web",
    ".md": "docs", ".rst": "docs", ".txt": "docs", ".pdf": "docs", ".doc": "docs", ".docx": "docs",
    ".pptx": "slides", ".ppt": "slides", ".key": "slides",
    ".csv": "data", ".tsv": "data", ".json": "data", ".jsonl": "data", ".parquet": "data", ".xlsx": "data",
    ".xls": "data", ".npy": "data", ".npz": "data", ".pkl": "data", ".h5": "data", ".db": "data", ".sqlite": "data",
    ".pt": "model-weights", ".pth": "model-weights", ".onnx": "model-weights", ".safetensors": "model-weights",
    ".ckpt": "model-weights", ".gguf": "model-weights", ".bin": "model-weights",
    ".png": "media", ".jpg": "media", ".jpeg": "media", ".gif": "media", ".svg": "media", ".mp4": "media",
    ".mov": "media", ".mp3": "media", ".wav": "media", ".webp": "media",
    ".yml": "config", ".yaml": "config", ".toml": "config", ".ini": "config", ".cfg": "config",
}


def file_census(files: list[tuple[str, int]]) -> dict:
    """Census of *all* files by category: a repo that is 90% slides must not be described as code."""
    cat_bytes: Counter = Counter()
    cat_files: Counter = Counter()
    exts: dict[str, Counter] = {}
    for rel, size in files:
        suffix = Path(rel).suffix.lower()
        if Path(rel).name.lower() == "desktop.ini":
            continue
        cat = CATEGORY_BY_EXT.get(suffix, "other")
        cat_bytes[cat] += size
        cat_files[cat] += 1
        exts.setdefault(cat, Counter())[suffix or "(none)"] += 1
    total = sum(cat_bytes.values()) or 1
    return {
        "total_files": sum(cat_files.values()),
        "categories": {c: {"files": cat_files[c], "share_bytes": round(cat_bytes[c] / total, 3),
                           "top_extensions": [e for e, _ in exts[c].most_common(3)]}
                       for c, _ in cat_bytes.most_common()},
    }


def detect_stack(root: Path) -> dict:
    lang_bytes: Counter = Counter()
    deps: dict[str, str] = {}
    manifests, lockfiles, all_paths, sized = [], [], [], []
    for rel, path, size in iter_files(root):
        all_paths.append(rel)
        sized.append((rel, size))
        name = path.name.lower()
        if (lang := LANG_BY_EXT.get(path.suffix.lower())):
            lang_bytes[lang] += size
        parser = MANIFESTS.get(name) or (_parse_requirements if re.fullmatch(r"requirements[-\w]*\.txt", name) else None)
        if parser:
            manifests.append(rel)
            deps.update(parser(read_text(path)))
        if name in LOCKFILES:
            lockfiles.append(rel)

    tags: Counter = Counter()
    matched = {}
    for dep in deps:
        base = dep.split("/")[-1] if "/" in dep else dep
        for key in (dep, base):
            if key in TAXONOMY:
                matched[dep] = TAXONOMY[key]
                tags.update(TAXONOMY[key])
                break

    total = sum(lang_bytes.values()) or 1
    pinned = sum(1 for v in deps.values() if v.startswith(("==", "v")) or re.match(r"^\d", v or ""))
    return {
        "languages": {k: round(v / total, 3) for k, v in lang_bytes.most_common(6)},
        "primary_language": lang_bytes.most_common(1)[0][0] if lang_bytes else None,
        "manifests": manifests,
        "lockfiles": lockfiles,
        "dependency_count": len(deps),
        "pinned_ratio": round(pinned / len(deps), 2) if deps else None,
        "capability_tags": [t for t, _ in tags.most_common()],
        "recognized_dependencies": sorted(matched),
        "dependencies": sorted(deps),
        "file_census": file_census(sized),
        "_paths": all_paths,
    }


def tags_for_imports(imports: list[dict]) -> list[str]:
    """Capability tags implied by third-party imports (works when a repo has no manifest)."""
    tags: list[str] = []
    for imp in imports:
        for key in (imp["name"].lower().replace("_", "-"), imp["module"].lower().replace("_", "-")):
            for tag in TAXONOMY.get(key, []):
                if tag not in tags:
                    tags.append(tag)
    return tags
