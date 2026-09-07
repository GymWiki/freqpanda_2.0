import pytest

from freqpanda_data.exchange import DEFAULT_PAGE_LIMIT, fetch_ohlcv_since, is_closed_candle

HOUR_MS = 3_600_000


class FakeExchange:
    """Stand-in for a ccxt.Exchange: serves fixed pages of candles from an
    in-memory list, so pagination logic can be tested without any network
    access or real CCXT rate limiting.
    """

    def __init__(self, all_candles, now_ms, page_limit=DEFAULT_PAGE_LIMIT):
        self._all_candles = all_candles
        self._now_ms = now_ms
        self._page_limit = page_limit
        self.calls = []

    def parse_timeframe(self, timeframe):
        assert timeframe == "1h"
        return 3600

    def milliseconds(self):
        return self._now_ms

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.calls.append(since)
        candidates = [c for c in self._all_candles if c[0] >= since]
        return candidates[:limit]


def _make_candles(start_ms, count, step_ms=HOUR_MS):
    return [[start_ms + i * step_ms, 1.0, 2.0, 0.5, 1.5, 100.0] for i in range(count)]


def test_fetch_ohlcv_since_single_page_when_caught_up():
    candles = _make_candles(0, 5)
    exchange = FakeExchange(candles, now_ms=candles[-1][0] + HOUR_MS, page_limit=100)
    pages = list(fetch_ohlcv_since(exchange, "BTC/USDT", "1h", since_ms=0, limit=100))
    assert len(pages) == 1
    assert pages[0] == candles


def test_fetch_ohlcv_since_paginates_until_caught_up():
    candles = _make_candles(0, 25)
    exchange = FakeExchange(candles, now_ms=candles[-1][0] + HOUR_MS, page_limit=10)
    pages = list(fetch_ohlcv_since(exchange, "BTC/USDT", "1h", since_ms=0, limit=10))
    assert [len(p) for p in pages] == [10, 10, 5]
    flattened = [c for page in pages for c in page]
    assert flattened == candles
    # Each page's "since" should follow directly from the previous page's
    # last candle, i.e. no gaps and no re-fetching already-seen candles.
    assert exchange.calls == [0, candles[9][0] + HOUR_MS, candles[19][0] + HOUR_MS]


def test_fetch_ohlcv_since_stops_when_no_candles_returned():
    exchange = FakeExchange([], now_ms=HOUR_MS * 10, page_limit=10)
    pages = list(fetch_ohlcv_since(exchange, "BTC/USDT", "1h", since_ms=0, limit=10))
    assert pages == []


def test_fetch_ohlcv_since_resumes_from_given_since_ms():
    candles = _make_candles(0, 10)
    resume_from = candles[5][0]
    exchange = FakeExchange(candles, now_ms=candles[-1][0] + HOUR_MS, page_limit=100)
    pages = list(fetch_ohlcv_since(exchange, "BTC/USDT", "1h", since_ms=resume_from, limit=100))
    assert pages == [candles[5:]]


@pytest.mark.parametrize(
    "offset_ms, expected",
    [(-1, False), (0, True), (1, True)],
)
def test_is_closed_candle(offset_ms, expected):
    candle_open_ms = 1_000_000
    timeframe_ms = HOUR_MS
    close_time_ms = candle_open_ms + timeframe_ms
    now_ms = close_time_ms + offset_ms
    assert is_closed_candle([candle_open_ms], timeframe_ms, now_ms) is expected
