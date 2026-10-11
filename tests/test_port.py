"""`python app.py` must not crash when port 5000 is already taken (e.g. AirPlay Receiver on Macs)."""
import socket

from app import pick_port


def test_free_port_is_used_as_is():
    with socket.socket() as s:
        s.bind(("0.0.0.0", 0))
        free = s.getsockname()[1]
    assert pick_port(free) == free


def test_busy_port_moves_to_the_next_free_one():
    with socket.socket() as busy:
        busy.bind(("0.0.0.0", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        chosen = pick_port(taken)
        assert chosen != taken and taken < chosen <= taken + 10
