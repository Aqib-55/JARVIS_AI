"""
Tests for MemoryManager:
- Facts storage, retrieval, and deletion
- User preferences
- Tool usage metrics
- Cross-domain memory search
- Context retrieval
- Memory deletion controls
"""

from memory.memory_manager import MemoryManager


class TestMemoryManager:

    def setup_method(self):
        pass

    def test_facts_lifecycle(self, db):
        mem = MemoryManager(db)

        # Add facts
        fid1 = mem.add_fact(category="preferences", fact="User prefers dark mode")
        fid2 = mem.add_fact(category="project", fact="Project root is D:\\JARVIS_AI")
        assert fid1 > 0
        assert fid2 > 0

        # Retrieve all
        all_facts = mem.get_facts()
        assert len(all_facts) == 2

        # Retrieve by category
        proj_facts = mem.get_facts(category="project")
        assert len(proj_facts) == 1
        assert "JARVIS_AI" in proj_facts[0]["fact"]

        # Delete fact
        deleted = mem.delete_fact(fid1)
        assert deleted is True
        assert len(mem.get_facts()) == 1

    def test_preferences_lifecycle(self, db):
        mem = MemoryManager(db)

        mem.set_preference("editor", "vscode")
        mem.set_preference("theme", "dracula")

        assert mem.get_preference("editor") == "vscode"
        assert mem.get_preference("missing", "default_val") == "default_val"

        all_prefs = mem.get_all_preferences()
        assert all_prefs["theme"] == "dracula"

        deleted = mem.delete_preference("editor")
        assert deleted is True
        assert mem.get_preference("editor") is None

    def test_tool_usage_metrics(self, db):
        mem = MemoryManager(db)

        mem.record_tool_usage("calculator", success=True)
        mem.record_tool_usage("calculator", success=True)
        mem.record_tool_usage("calculator", success=False)
        mem.record_tool_usage("list_files", success=True)

        freq = mem.get_frequently_used_tools()
        assert len(freq) >= 2
        calc_stat = next(t for t in freq if t["tool_name"] == "calculator")
        assert calc_stat["call_count"] == 3
        assert calc_stat["success_count"] == 2
        assert calc_stat["failure_count"] == 1

    def test_memory_search(self, db):
        mem = MemoryManager(db)

        mem.add_fact("project", "Python 3.13 is used for JARVIS AI")

        results = mem.search_memory("Python")
        assert len(results["facts"]) >= 1
        assert "Python 3.13" in results["facts"][0]["fact"]

    def test_get_relevant_context(self, db):
        mem = MemoryManager(db)

        mem.set_preference("user_name", "Raqib")
        mem.add_fact("work", "Working on AI automation agent")

        context = mem.get_relevant_context("AI automation")
        assert "User Preferences" in context
        assert "Raqib" in context
        assert "Relevant Known Facts" in context

    def test_clear_all_memory(self, db):
        mem = MemoryManager(db)
        mem.add_fact("temp", "To be wiped")

        mem.clear_all_memory(confirm=False)
        assert len(mem.get_facts()) == 1

        mem.clear_all_memory(confirm=True)
        assert len(mem.get_facts()) == 0
