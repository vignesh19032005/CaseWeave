"""
Stage 14 — sandboxed extraction entry point. Run via
`python -m pipeline.extract_worker <type> <path>`, invoked through
upload_validation.run_extraction_sandboxed() as a subprocess instead of
in-process, so a malformed/malicious file crashes this throwaway process,
not the API server. Prints a single JSON line to stdout; any failure exits
non-zero with the error on stderr.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.extract import extract_pdf, extract_image_ocr


def main():
    if len(sys.argv) != 3:
        print("usage: python -m pipeline.extract_worker <pdf|image> <path>", file=sys.stderr)
        sys.exit(2)

    kind, path_str = sys.argv[1], sys.argv[2]
    path = Path(path_str)

    try:
        if kind == "pdf":
            result = extract_pdf(path)
        elif kind == "image":
            result = extract_image_ocr(path)
        else:
            raise ValueError(f"unsupported extraction kind: {kind}")
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
