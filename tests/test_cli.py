from __future__ import annotations

import pytest

from hoseki.__main__ import main


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == "hoseki 0.3.2\n"
