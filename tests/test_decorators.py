import pytest
from src.sdk.decorators import on_event, task, agent


class TestOnEvent:
    def test_valid_event_type(self):
        """on_event with a proper event_type should work."""
        @on_event("user.created")
        def handler(data):
            pass

        assert handler.__event_handler__ == "user.created"

    def test_empty_event_type_raises(self):
        """on_event with empty string should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty event_type"):
            @on_event("")
            def handler(data):
                pass

    def test_whitespace_event_type_raises(self):
        """on_event with whitespace-only string should raise ValueError."""
        with pytest.raises(ValueError, match="non-empty event_type"):
            @on_event("   ")
            def handler(data):
                pass

    def test_event_type_with_spaces_preserved(self):
        """on_event with actual content (including spaces) should work."""
        @on_event("order.shipped v2")
        def handler(data):
            pass

        assert handler.__event_handler__ == "order.shipped v2"


class TestTaskDecorator:
    def test_task_default_name(self):
        @task()
        def my_task():
            pass

        assert my_task.__task_config__["name"] == "my_task"

    def test_task_custom_name(self):
        @task(name="custom_name")
        def my_task():
            pass

        assert my_task.__task_config__["name"] == "custom_name"


class TestAgentDecorator:
    def test_agent_config(self):
        @agent("test-agent", version="2.0.0")
        class TestAgent:
            pass

        assert TestAgent.__agent_config__["name"] == "test-agent"
        assert TestAgent.__agent_config__["version"] == "2.0.0"
