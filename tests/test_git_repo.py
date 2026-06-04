import sys

from javadoc_miner.git_repo import _run


def test_run_decodes_utf8_output_independent_of_windows_locale():
    output = _run(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write('☃'.encode('utf-8'))",
        ],
        cwd=None,
    )

    assert output == "☃"
