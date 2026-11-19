import importlib
import sys

MODULES = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic_settings",
    "dotenv",
    "yt_dlp",
    "moviepy",
    "cv2",
    "whisper",
    "transformers",
    "sentence_transformers",
    "pydub",
    "librosa",
    "soundfile",
    "requests",
    "bs4",
    "loguru",
    "numpy",
    "PIL",
    "tqdm",
)


def main() -> int:
    if sys.version_info < (3, 11):
        print(f"Python 3.11+ is required; found {sys.version.split()[0]}", file=sys.stderr)
        return 1

    failed = False
    for module_name in MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError as error:
            failed = True
            print(f"MISSING {module_name}: {error}")
        else:
            print(f"OK      {module_name}")

    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
