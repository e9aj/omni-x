import base64
import pytest

from omnix.brain import MarkdownVault, VaultError
from omnix.store import Store
from omnix.semantic_index import SemanticIndex


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


def test_brain_attachment_is_contained_and_bounded(tmp_path):
    vault = MarkdownVault(tmp_path / "brain")
    path = vault.save_attachment("source.txt", base64.b64encode(b"evidence").decode())
    assert path == "source.txt"
    assert vault.list_attachments()[0]["path"] == "source.txt"
    with pytest.raises(VaultError):
        vault.save_attachment("../escape.txt", base64.b64encode(b"no").decode())


def test_brain_note_history_is_portable_and_excludes_history_from_notes(tmp_path):
    vault = MarkdownVault(tmp_path / "brain")
    vault.write("note.md", "first")
    vault.write("note.md", "second")
    assert vault.read("note.md") == "second"
    assert len(vault.history("note.md")) == 1
    assert [item["path"] for item in vault.list_notes()] == ["note.md"]


def test_local_semantic_index_is_persistent_and_deterministic(tmp_path):
    vault = MarkdownVault(tmp_path / "brain")
    vault.write("python.md", "Python packaging and Windows installer")
    vault.write("garden.md", "Tomatoes and herbs in the garden")
    store = Store(tmp_path / "state.sqlite3")
    index = SemanticIndex(store, tmp_path / "brain")
    assert index.rebuild(((str(item["path"]), vault.read(str(item["path"]))) for item in vault.list_notes())) == 2
    assert index.search("Windows Python")[0]["path"] == "python.md"
    reopened = SemanticIndex(Store(tmp_path / "state.sqlite3"), tmp_path / "brain")
    assert reopened.search("garden")[0]["path"] == "garden.md"


def test_neural_embedding_requires_an_existing_local_model(tmp_path):
    with pytest.raises(ValueError, match="local embedding model"):
        SemanticIndex.neural_vector("private note", tmp_path / "missing-model")
