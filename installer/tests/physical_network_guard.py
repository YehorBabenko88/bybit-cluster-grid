"""Dedicated synthetic CI plugin: disallow IP/DB connections in test process."""
import socket
import pytest
import asyncpg
_CONNECT=socket.socket.connect
_CONNECT_EX=socket.socket.connect_ex

def connect(sock,address):
    if sock.family in (socket.AF_INET,socket.AF_INET6):raise RuntimeError('PHYSICAL_FIXTURE_NETWORK_FORBIDDEN')
    return _CONNECT(sock,address)
def connect_ex(sock,address):
    if sock.family in (socket.AF_INET,socket.AF_INET6):raise RuntimeError('PHYSICAL_FIXTURE_NETWORK_FORBIDDEN')
    return _CONNECT_EX(sock,address)
@pytest.fixture(autouse=True)
def forbid_real_ip_and_database(monkeypatch):
    def denied(*a,**k):raise RuntimeError('PHYSICAL_FIXTURE_DATABASE_FORBIDDEN')
    monkeypatch.setattr(socket.socket,'connect',connect)
    monkeypatch.setattr(socket.socket,'connect_ex',connect_ex)
    monkeypatch.setattr(asyncpg,'connect',denied)
    monkeypatch.setattr(asyncpg,'create_pool',denied)
