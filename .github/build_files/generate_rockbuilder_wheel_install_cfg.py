from pathlib import Path
import sys

def verify_and_generate_config(
    template_version: str,
    template_target_gpu: str,
    config_file: Path,
) -> None:
    """Verify parameters and generate rockbbuilder.cfg."""
    for name, value in {
        "template_version": template_version,
        "template_target_gpu": template_target_gpu,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    if not isinstance(config_file, Path):
        raise ValueError("config_file must be a pathlib.Path")

    config_content = f"""[rocm_sdk]
rocm_sdk_whl_server = ['https://rocm.nightlies.amd.com/v2/']
rocm_sdk_whl_version = {template_version}

[build_targets]
gpus = ['{template_target_gpu}']
"""

    config_file.write_text(config_content)
    print(f"Generated {config_file.resolve()}")


def main() -> None:
    """
    Entry point.
    Usage:
        python generate_config.py <template_version> <template_target_gpu> <config_file>
    """
    if len(sys.argv) != 4:
        print(
            "Usage: python generate_config.py <template_version> <template_target_gpu> <config_file>",
            file=sys.stderr,
        )
        sys.exit(1)

    template_version = sys.argv[1]
    template_target_gpu = sys.argv[2]
    config_file = Path(sys.argv[3])

    try:
        verify_and_generate_config(
            template_version,
            template_target_gpu,
            config_file,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
