# Detectors

Detectors analyse each incoming price aggregate and emit an alert when a condition is met. Each detector is identified by a **kind** string used in the config file.

---

## Configuration

Detectors are configured in `config/config.yaml` under `portfolio_monitor.monitors`.

- `default` — detectors applied to every tracked asset.
- Any other key is treated as a **ticker symbol** and applies additional detectors to that asset only.

```yaml
portfolio_monitor:
  monitors:
    default:
      SMA_deviation:
        period: "4h"
        threshold: 0.03
      volume_spike: {}          # use all defaults

    AAPL:                       # per-asset override
      percent_change:
        period: "2d"
        threshold: 0.05
```

Omitting a parameter block (`{}`) or leaving a key empty uses the detector's defaults.

### Period format

Time-based `period` parameters accept a numeric value followed by a unit suffix:

| Suffix | Unit    | Example |
|--------|---------|---------|
| `s`    | seconds | `"30s"` |
| `m`    | minutes | `"15m"` |
| `h`    | hours   | `"2h"`  |
| `d`    | days    | `"1d"`  |

---

## Detectors

### `percent_change`

Alerts when the price moves by more than a threshold compared to the price from a **configurable time period ago**. Maintains a rolling history so the reference price tracks the configured look-back correctly.

| Parameter   | Type    | Default | Description |
|-------------|---------|---------|-------------|
| `threshold` | `float` | `0.03`  | Fractional change that triggers an alert (e.g. `0.03` = 3%). |
| `period`    | `str`   | `"1d"`  | How far back the reference price is taken from. |

**Alert extra fields**

| Field            | Type    | Description |
|------------------|---------|-------------|
| `percent_change` | `float` | Signed percentage change from the reference price. |

**Example**

```yaml
percent_change:
  period: "4h"
  threshold: 0.02   # alert on 2% moves over the past 4 hours
```

---

### `SMA_deviation`

Alerts when the current price deviates from the **Simple Moving Average** of closing prices over a rolling time window. Useful for detecting sustained trend breaks or mean-reversion signals.

| Parameter   | Type    | Default | Description |
|-------------|---------|---------|-------------|
| `period`    | `str`   | `"2h"`  | Rolling window for the SMA calculation. |
| `threshold` | `float` | `0.05`  | Fractional deviation from the SMA that triggers an alert (e.g. `0.05` = 5%). |

**Alert extra fields**

| Field                   | Type    | Description |
|-------------------------|---------|-------------|
| `deviation_percent`     | `float` | Absolute percentage deviation from the SMA. |
| `simple_moving_average` | `float` | Current SMA value. |
| `period`                | `str`   | Configured period string. |

**Example**

```yaml
SMA_deviation:
  period: "1h"
  threshold: 0.03   # alert when price is >3% away from the 1-hour SMA
```

---

### `volume_spike`

Alerts when the current bar's trading volume exceeds a multiple of the **average volume** over a rolling time window.

| Parameter   | Type    | Default | Description |
|-------------|---------|---------|-------------|
| `period`    | `str`   | `"2h"`  | Rolling window for average volume calculation. |
| `threshold` | `float` | `2.0`   | Multiple of average volume that triggers an alert (e.g. `2.0` = 2× average). |

**Alert extra fields**

| Field              | Type    | Description |
|--------------------|---------|-------------|
| `current_volume`   | `float` | Volume of the triggering bar. |
| `average_volume`   | `float` | Mean volume over the configured window. |
| `percent_increase` | `float` | Volume increase above the average as a percentage. |
| `period`           | `str`   | Configured period string. |

**Example**

```yaml
volume_spike:
  period: "1h"
  threshold: 3.0    # alert only on 3× average volume spikes
```

---

### `zscore_return`

Alerts when the current bar's **price return** (close-to-close percentage change) is a statistically unusual number of standard deviations away from the distribution of recent returns. Requires at least 3 data points to compute.

| Parameter   | Type    | Default | Description |
|-------------|---------|---------|-------------|
| `period`    | `str`   | `"2h"`  | Rolling window for return distribution statistics. |
| `threshold` | `float` | `2.0`   | Z-score magnitude that triggers an alert (e.g. `2.0` = 2 standard deviations). |

**Alert extra fields**

| Field                    | Type    | Description |
|--------------------------|---------|-------------|
| `z_score`                | `float` | Signed Z-score of the current return. |
| `current_return_percent` | `float` | Current bar's return as a percentage. |
| `average_return_percent` | `float` | Mean return over the window as a percentage. |
| `standard_deviation`     | `float` | Standard deviation of returns over the window. |
| `period`                 | `str`   | Configured period string. |

**Example**

```yaml
zscore_return:
  period: "4h"
  threshold: 2.5    # alert on returns >2.5σ from the 4-hour mean
```

---

### `zscore_volume`

Alerts when the current bar's volume is a statistically unusual number of standard deviations **above** the mean volume over a rolling window. More robust than a fixed multiple because it adapts to the asset's natural volume variability. Requires at least 2 data points.

| Parameter   | Type    | Default | Description |
|-------------|---------|---------|-------------|
| `period`    | `str`   | `"2h"`  | Rolling window for volume distribution statistics. |
| `threshold` | `float` | `1.0`   | Z-score threshold that triggers an alert (e.g. `1.0` = 1 standard deviation above mean). |

**Alert extra fields**

| Field                | Type    | Description |
|----------------------|---------|-------------|
| `z_score`            | `float` | Z-score of the current volume. |
| `current_volume`     | `float` | Volume of the triggering bar. |
| `average_volume`     | `float` | Mean volume over the configured window. |
| `standard_deviation` | `float` | Standard deviation of volume over the window. |
| `period`             | `str`   | Configured period string. |

**Example**

```yaml
zscore_volume:
  period: "2h"
  threshold: 2.0    # alert only on volume >2σ above the 2-hour mean
```

---

### `average_true_range_move`

Alerts when the current bar's **high-low range** exceeds a multiple of the **Average True Range (ATR)** calculated over a rolling sample window. ATR accounts for overnight gaps by incorporating the previous bar's close in the true-range calculation. Requires `period + 1` samples before it can fire.


| Parameter   | Type    | Default | Description |
|-------------|---------|---------|-------------|
| `samples`   | `int`   | `30`    | Number of bars used to calculate the ATR. |
| `threshold` | `float` | `2.0`   | Multiple of ATR that triggers an alert (e.g. `2.0` = current range is ≥2× ATR). |

**Alert extra fields**

| Field                | Type    | Description |
|----------------------|---------|-------------|
| `current_range`      | `float` | High − low of the triggering bar. |
| `average_true_range` | `float` | ATR value over the configured window. |
| `range_multiple`     | `float` | Current range expressed as a multiple of ATR. |

**Example**

```yaml
average_true_range_move:
  samples: 20        # 20-bar ATR
  threshold: 2.5    # alert when bar range exceeds 2.5× ATR
```
