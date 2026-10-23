"""Compile repository Python sources in memory without importing or writing pyc."""

from pathlib import Path
import sys
import tokenize


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__"}


def python_sources():
    candidates = list(ROOT.rglob("*.py"))
    cli = ROOT / "bin" / "yuva"
    if cli.is_file():
        candidates.append(cli)
    return sorted(
        (path for path in candidates
         if not any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts)),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def main():
    sources = python_sources()
    if not sources:
        print("syntax check found no Python source files", file=sys.stderr)
        return 2

    for path in sources:
        relative = path.relative_to(ROOT).as_posix()
        try:
            with tokenize.open(path) as stream:
                source = stream.read()
            compile(source, relative, "exec")
        except SyntaxError as error:
            print(f"{relative}:{error.lineno or 0}: syntax error: {error.msg}",
                  file=sys.stderr)
            return 1
        except (OSError, UnicodeError) as error:
            print(f"{relative}: cannot read source ({type(error).__name__})",
                  file=sys.stderr)
            return 1

    print(f"Python syntax OK: {len(sources)} source files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
