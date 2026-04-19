"""
Smoke test for _speak_streaming — proves the queue/consumer + sentence-boundary
logic works without needing Ollama, Whisper, or a real TTS daemon.

Feeds synthetic token chunks into the queue exactly the way _chat_with_tools
would during streaming, captures every "sentence" the consumer dispatches to
the (mocked) speak(), and asserts the splitting matches expectations.

Run: uv run python test_streaming_tts.py
"""

import asyncio
import sys

from agent_friday import _speak_streaming


async def _drive(chunks: list[str]) -> list[str]:
    """Feed chunks + None sentinel through _speak_streaming, return what was spoken."""
    spoken: list[str] = []

    async def fake_speak(text: str) -> None:
        spoken.append(text)

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_speak_streaming(queue, fake_speak))
    for tok in chunks:
        queue.put_nowait(tok)
    queue.put_nowait(None)
    await task
    return spoken


async def test_speaks_sentences_as_they_land():
    got = await _drive(["It's ", "11:42 PM, ", "boss. ", "Markets ", "look fine."])
    expected = ["It's 11:42 PM, boss.", "Markets look fine."]
    assert got == expected, f"expected {expected}, got {got}"


async def test_handles_tail_without_trailing_space():
    got = await _drive(["Got it."])
    assert got == ["Got it."], f"got {got}"


async def test_empty_stream_speaks_nothing():
    got = await _drive([])
    assert got == [], f"got {got}"


async def test_abbreviation_with_trailing_space_splits_naively():
    # KNOWN LIMITATION: the splitter treats any ". " as a boundary, so
    # "U.S. markets" gets split into "U.S." and "markets…".  Real-world
    # fix would be an abbreviation dictionary; not worth it for FRIDAY's
    # short conversational replies which are abbreviation-light.  This
    # test pins the current behavior so regressions are visible.
    got = await _drive(["U.S. ", "markets closed up. "])
    assert got == ["U.S.", "markets closed up."], f"got {got}"


async def test_multiple_sentences_in_single_chunk():
    got = await _drive(["One. Two! Three? Four."])
    assert got == ["One.", "Two!", "Three?", "Four."], f"got {got}"


async def main() -> int:
    tests = [
        test_speaks_sentences_as_they_land,
        test_handles_tail_without_trailing_space,
        test_empty_stream_speaks_nothing,
        test_abbreviation_with_trailing_space_splits_naively,
        test_multiple_sentences_in_single_chunk,
    ]
    failed = 0
    for t in tests:
        try:
            await t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
