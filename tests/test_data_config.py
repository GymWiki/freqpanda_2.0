import json

from freqpanda_data import PipelineConfig, SymbolTimeframe, load_pipeline_config


def test_from_dict_builds_symbol_timeframe_pairs():
    config = PipelineConfig.from_dict(
        {
            "exchange_id": "binance",
            "pairs": [{"symbol": "BTC/USDT", "timeframe": "1h"}],
            "backfill_since": "2021-01-01T00:00:00Z",
        }
    )
    assert config.exchange_id == "binance"
    assert config.pairs == [SymbolTimeframe(symbol="BTC/USDT", timeframe="1h")]
    assert config.backfill_since == "2021-01-01T00:00:00Z"


def test_defaults_when_fields_omitted():
    config = PipelineConfig.from_dict({})
    assert config.exchange_id == "binance"
    assert config.pairs == []
    assert config.database_url is None


def test_load_pipeline_config_from_file(tmp_path):
    path = tmp_path / "pipeline.json"
    path.write_text(
        json.dumps(
            {
                "exchange_id": "kraken",
                "pairs": [
                    {"symbol": "BTC/USDT", "timeframe": "1h"},
                    {"symbol": "ETH/USDT", "timeframe": "4h"},
                ],
            }
        )
    )
    config = load_pipeline_config(path)
    assert config.exchange_id == "kraken"
    assert len(config.pairs) == 2
    assert config.pairs[1] == SymbolTimeframe(symbol="ETH/USDT", timeframe="4h")


def test_example_pipeline_config_loads():
    config = load_pipeline_config("config/pipeline.json")
    assert config.exchange_id == "binance"
    assert len(config.pairs) >= 1
