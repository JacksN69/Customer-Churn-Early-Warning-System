"""Phase 2 wrapper: raw transaction audit -> reports/data_quality_raw.md."""
import runpy

from src import config


def main():
    runpy.run_path(str(config.PROJECT_ROOT / "scripts" / "audit_raw.py"), run_name="__main__")


if __name__ == "__main__":
    main()

