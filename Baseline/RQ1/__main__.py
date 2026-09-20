from .runner import main
import sys

if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as exc:
        print(f"[RQ1] {exc}", file=sys.stderr)
        raise SystemExit(1) from None
