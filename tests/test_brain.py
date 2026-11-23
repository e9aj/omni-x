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


def test_brain_graph_backlinks_and_document_inspection(tmp_path):
    vault = MarkdownVault(tmp_path / "brain")
    vault.write("alpha.md", "# Alpha\nLinks to [[beta]].")
    vault.write("beta.md", "## Beta\nKnowledge.")
    assert vault.graph()["edges"] == [{"source": "alpha.md", "target": "beta.md"}]
    assert vault.backlinks("beta.md") == ["alpha.md"]
    inspected = vault.inspect("beta.md")
    assert inspected["headings"] == ["Beta"]
    assert inspected["word_count"] == 3
