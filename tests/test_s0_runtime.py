"""Offline structural guardrails: parse source without importing runtime or doing I/O."""
import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 's0_smoke' / 'runtime.py'


def source_tree():
    assert SOURCE.is_file(), 'standalone S0 runtime must exist'
    return ast.parse(SOURCE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('name,arguments', [
    ('coordinator', ['config', 'root', 'journal', 'guard']),
    ('worker', ['config', 'root', 'journal', 'market_journal', 'guard']),
    ('public_connection', ['session']),
])
def test_runtime_async_component_contract(name, arguments):
    definitions = {node.name: node for node in source_tree().body if isinstance(node, ast.AsyncFunctionDef)}
    assert name in definitions
    definition = definitions[name]
    positional = [arg.arg for arg in definition.args.args]
    assert positional[:len(arguments)] == arguments
    if name != 'public_connection':
        defaults = dict(zip(positional[-len(definition.args.defaults):], definition.args.defaults))
        defaults.update(zip((a.arg for a in definition.args.kwonlyargs), definition.args.kw_defaults))
        assert ast.literal_eval(defaults['seconds']) == 300


def test_runtime_has_no_production_or_database_imports():
    forbidden = {'grid', 'installer', 'asyncpg', 'psycopg', 'psycopg2', 'sqlite3', 'pybit', 'ccxt', 'dotenv', 'telegram'}
    for node in ast.walk(source_tree()):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split('.')[0] in forbidden for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or '').split('.')[0] not in forbidden
