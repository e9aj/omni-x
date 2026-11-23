import pytest

from omnix.brain import MarkdownVault, VaultError


def test_vault_writes_reads_lists_and_searches(tmp_path):
    vault = MarkdownVault(tmp_path / "vault")
    vault.write("projects/alpha.md", "# Alpha\nOMNI-X Brain evidence")
    assert vault.read("projects/alpha.md").startswith("# Alpha")
    assert vault.search("evidence")[0]["path"] == "projects/alpha.md"
    assert vault.list_notes()[0]["path"] == "projects/alpha.md"


def test_vault_rejects_escape_and_non_markdown(tmp_path):
    vault = MarkdownVault(tmp_path / "vault")
    with pytest.raises(VaultError):
        vault.write("../outside.md", "no")
    with pytest.raises(VaultError):
        vault.write("unsafe.txt", "no")
