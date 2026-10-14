"""The token must never sit in config.json in clear text (Windows)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scribe import config as cfgmod  # noqa: E402
from scribe import secretstore  # noqa: E402


@pytest.fixture
def windows(monkeypatch):
    """Pretend we are on Windows and stand in for the DPAPI calls.

    The fake honours the entropy argument, so we can prove a token sealed
    before the rename (old entropy) still decrypts.
    """
    def encrypt(raw: bytes, entropy: bytes = secretstore._ENTROPY) -> bytes:
        return b"enc:" + entropy + b"\x00" + raw[::-1]

    def decrypt(raw: bytes, entropy: bytes = secretstore._ENTROPY) -> bytes:
        if not raw.startswith(b"enc:"):       # DPAPI verifies integrity too
            raise OSError("bad DPAPI blob")
        used, _, payload = raw[4:].partition(b"\x00")
        if used != entropy:
            raise OSError("wrong DPAPI entropy")
        return payload[::-1]

    monkeypatch.setattr(secretstore, "available", lambda: True)
    monkeypatch.setattr(secretstore, "_encrypt", encrypt)
    monkeypatch.setattr(secretstore, "_decrypt", decrypt)


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(tmp_path / "config.json"))
    return tmp_path


# ------------------------------------------------------------- secretstore --


def test_plain_text_passes_through_when_dpapi_is_unavailable(monkeypatch):
    monkeypatch.setattr(secretstore, "available", lambda: False)
    assert secretstore.protect("hunter2") == "hunter2"
    assert secretstore.unprotect("hunter2") == "hunter2"


def test_protect_roundtrip(windows):
    sealed = secretstore.protect("hunter2")
    assert sealed != "hunter2"
    assert sealed.startswith(secretstore.PREFIX)
    assert "hunter2" not in sealed
    assert secretstore.unprotect(sealed) == "hunter2"


def test_protect_is_idempotent(windows):
    sealed = secretstore.protect("hunter2")
    assert secretstore.protect(sealed) == sealed


def test_empty_values_are_left_alone(windows):
    assert secretstore.protect("") == ""
    assert secretstore.unprotect("") == ""


def test_windows_blob_cannot_be_read_elsewhere(windows, monkeypatch):
    sealed = secretstore.protect("hunter2")
    monkeypatch.setattr(secretstore, "available", lambda: False)
    with pytest.raises(OSError):
        secretstore.unprotect(sealed)


def test_token_sealed_before_the_rename_still_decrypts(windows):
    """A token encrypted with the old DPAPI entropy must keep working."""
    import base64

    legacy_blob = (b"enc:" + secretstore._LEGACY_ENTROPY[0] + b"\x00"
                   + b"hunter2"[::-1])
    value = secretstore.PREFIX + base64.b64encode(legacy_blob).decode("ascii")
    assert secretstore.unprotect(value) == "hunter2"


# ------------------------------------------------------------------- config --


def test_saved_config_has_no_plain_token(windows, tmp_config):
    cfg = cfgmod.load()
    cfg["token"] = "super-secret"
    cfgmod.save(cfg)

    raw = json.loads((tmp_config / "config.json").read_text())
    assert "token" not in raw
    assert "super-secret" not in (tmp_config / "config.json").read_text()
    assert raw["token_enc"].startswith(secretstore.PREFIX)

    # and the app still sees it in clear text in memory
    assert cfgmod.load()["token"] == "super-secret"


def test_config_file_is_owner_only(windows, tmp_config):
    if os.name != "posix":
        # Windows has no POSIX mode bits: os.chmod only toggles the read-only
        # flag, and the protection there is DPAPI + the user's own ACL.
        pytest.skip("POSIX file modes do not exist on Windows")
    cfg = cfgmod.load()
    cfg["token"] = "t"
    cfgmod.save(cfg)
    assert oct(os.stat(tmp_config / "config.json").st_mode)[-3:] == "600"


def test_old_plain_text_token_is_migrated_on_save(windows, tmp_config):
    """Upgrading from an older version must not lose the token."""
    (tmp_config / "config.json").write_text(json.dumps({"token": "legacy", "hotkey": "f9"}))

    cfg = cfgmod.load()
    assert cfg["token"] == "legacy"          # still usable
    assert cfg["token_encrypted"] is False   # nothing encrypted yet

    cfgmod.save(cfg)
    raw = json.loads((tmp_config / "config.json").read_text())
    assert "token" not in raw
    assert cfgmod.load()["token"] == "legacy"


def test_unreadable_token_does_not_crash_startup(windows, tmp_config, capsys):
    (tmp_config / "config.json").write_text(
        json.dumps({"token_enc": secretstore.PREFIX + "Z2FyYmFnZQ==", "hotkey": "f9"}))

    cfg = cfgmod.load()                      # must not raise
    assert cfg["token"] == ""
    assert "could not decrypt" in capsys.readouterr().err


def test_missing_config_has_an_empty_token(tmp_config):
    assert cfgmod.load()["token"] == ""


def test_config_folder_migrates_from_the_old_name(tmp_path, monkeypatch):
    """Upgrading from VozLab must carry the settings and log across, once."""
    old = tmp_path / "VozLab"
    new = tmp_path / "Scribe"
    old.mkdir()
    (old / "config.json").write_text(
        json.dumps({"server_host": "192.168.0.23", "token": "t"}))
    (old / "vozlab.log").write_text("hello\n")
    monkeypatch.setattr(cfgmod, "config_dir", lambda: str(new))
    monkeypatch.setattr(cfgmod, "legacy_config_dir", lambda: str(old))

    assert cfgmod.migrate_legacy_config() is True
    assert (new / "config.json").exists()
    assert (new / "scribe.log").read_text() == "hello\n"
    assert cfgmod.load()["server_host"] == "192.168.0.23"
    # idempotent: there is nothing left to migrate the second time
    assert cfgmod.migrate_legacy_config() is False


# --------------------------------------------------------------- log scrubbing --


@pytest.fixture
def logfile(tmp_path, monkeypatch):
    from scribe import log as logmod
    path = tmp_path / "scribe.log"
    monkeypatch.setattr(logmod, "_log_path", str(path))
    monkeypatch.setattr(logmod, "_console", None)
    logmod.set_secrets([])
    return logmod, path


def test_log_file_never_contains_the_token(logfile):
    logmod, path = logfile
    logmod.set_secrets(["s3cret-token-value"])
    logmod.log("connecting with token s3cret-token-value to the server")
    contents = path.read_text()
    assert "s3cret-token-value" not in contents
    assert "***" in contents


def test_redact_masks_authorization_headers_and_json(logfile):
    logmod, _ = logfile
    assert logmod.redact("Authorization: Bearer abc123def456") == "Authorization: Bearer ***"
    assert logmod.redact('{"token": "abc123def456"}') == '{"token": "***"}'
    assert logmod.redact("token=abc123def456") == "token=***"


def test_log_read_tails_and_clear_empties(logfile):
    logmod, path = logfile
    for i in range(30):
        logmod.log(f"line {i}")
    tail = logmod.read(lines=5).splitlines()
    assert len(tail) == 5
    assert [line.rsplit(" ", 1)[-1] for line in tail] == [f"{i}" for i in range(25, 30)]

    assert logmod.clear() is True
    assert path.read_text() == ""
    assert logmod.read() == ""


def test_short_values_are_not_treated_as_secrets(logfile):
    """A 3-character 'secret' would mask half the log."""
    logmod, path = logfile
    logmod.set_secrets(["abc", "", None])
    logmod.log("abc def ghi")
    assert "abc def ghi" in path.read_text()
