from __future__ import annotations

import sys
from types import ModuleType

from openresearchgraph.memory import PostgresMilvusMemory


class FakeCursor:
    def __init__(self) -> None:
        self.row = None

    def execute(self, query, params=None):
        if str(query).startswith("SELECT"):
            self.row = ("历史摘要", {"tone": "brief"})
        return self

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakePsycopg(ModuleType):
    def connect(self, dsn):
        return FakeCursor()


class FakeMilvusClient:
    def __init__(self, **options) -> None:
        self.options = options
        self.created = False
        self.items = []

    def has_collection(self, collection_name):
        return self.created

    def create_collection(self, **options):
        self.created = True

    def upsert(self, collection_name, data):
        self.items.extend(data)

    def search(self, **options):
        return [[{"entity": {"content": "长期语义记忆"}}]]


def test_postgres_milvus_memory_contract(monkeypatch) -> None:
    pymilvus = ModuleType("pymilvus")
    pymilvus.MilvusClient = FakeMilvusClient
    monkeypatch.setitem(sys.modules, "psycopg", FakePsycopg("psycopg"))
    monkeypatch.setitem(sys.modules, "pymilvus", pymilvus)

    memory = PostgresMilvusMemory(
        postgres_dsn="postgresql://example.invalid/research",
        milvus_uri="http://milvus.invalid:19530",
    )
    memory.remember_session("session", "本轮摘要", {"tone": "brief"})
    memory.remember_knowledge("一条长期知识", {"synthetic": True}, "memory-1")
    recalled = memory.recall("session", "长期知识")

    assert recalled[0] == "会话摘要：本轮摘要"
    assert "表达偏好：tone=brief" in recalled
    assert "长期语义记忆" in recalled
    assert memory._milvus.items[0]["id"] == "memory-1"
