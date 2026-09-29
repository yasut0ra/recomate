"""Minimal stand-in for the OpenAI client's chat.completions interface."""

import json
from types import SimpleNamespace


class FakeOpenAI:
    def __init__(self, responder=None, error=None):
        self.responder = responder
        self.error = error
        self.calls = []
        self.options = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def with_options(self, **options):
        self.options.append(options)
        return self

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        content = self.responder(kwargs)
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def schema_of(call):
    return call["response_format"]["json_schema"]["schema"]
