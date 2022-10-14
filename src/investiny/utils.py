# Copyright 2022 Alvaro Bartolome, alvarobartt @ GitHub
# See LICENSE for details.

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Tuple, Union
from uuid import uuid4

import httpx

from investiny.config import Config

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)


def request_to_investing(
    endpoint: Literal["history", "search"], params: Dict[str, Any]
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Sends an HTTP GET request to Investing.com API with the introduced params.

    Args:
        endpoint (Literal["history", "search"]): Endpoint to send the request to.
        params (Dict[str, Any]): A dictionary with the params to send to Investing.com API.

    Returns:
        Dict[str, Any]: A dictionary with the response from Investing.com API.
    """
    url = f"https://tvc4.investing.com/{uuid4().hex}/0/0/0/0/{endpoint}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like"
            " Gecko) Chrome/104.0.5112.102 Safari/537.36"
        ),
        "Referer": "https://tvc-invdn-com.investing.com/",
        "Content-Type": "application/json",
    }
    r = httpx.get(url, params=params, headers=headers)
    if r.status_code != 200:
        raise ConnectionError(
            f"Request to Investing.com API failed with error code: {r.status_code}."
        )
    d = r.json()

    if endpoint == "history" and d["s"] != "ok":
        raise ConnectionError(
            f"Request to Investing.com API failed with error message: {d['s']}."
            if "nextTime" not in d
            else (
                f"Request to Investing.com API failed with error message: {d['s']}, the"
                " market was probably closed in the introduced dates, try again with"
                f" `from_date={datetime.fromtimestamp(d['nextTime'], tz=timezone.utc).strftime(Config.date_format)}`."
            )
        )
    return d  # type: ignore


def calculate_date_intervals(
    from_date: Union[str, None] = None,
    to_date: Union[str, None] = None,
    interval: Literal[1, 5, 15, 30, 45, 60, 120, 240, 300, "D", "W", "M"] = "D",
) -> Tuple[List[datetime], List[datetime]]:
    """Calculates the intervals between the introduced dates.

    Args:
        from_date (Union[str, None], optional): Initial date to retrieve historical data (formatted as m/d/Y). Defaults to None.
        to_date (Union[str, None], optional): Final date to retrieve historical data (formatted as m/d/Y). Defaults to None.
        interval (Literal[1, 5, 15, 30, 45, 60, 120, 240, 300, "D", "W", "M"]): Interval between each historical data point. Defaults to "D".

    Returns:
        Tuple[List[str], List[str]]: A tuple with the from and to datetimes split by intervals.
    """
    interval2timedelta = {
        1: timedelta(minutes=30),  # 30 minutes (half an hour)
        5: timedelta(hours=1),  # 1 hour
        15: timedelta(hours=3),  # 3 hours
        30: timedelta(hours=6),  # 6 hours
        45: timedelta(hours=12),  # 12 hours (half a day)
        60: timedelta(hours=24),  # 24 hours (one day)
        120: timedelta(hours=48),  # 48 hours (two days)
        240: timedelta(hours=96),  # 96 hours (four days)
        300: timedelta(hours=120),  # 120 hours (five days)
        "D": timedelta(days=30),  # 30 days (~ 1 month)
        "W": timedelta(days=90),  # 3 months
        "M": timedelta(days=365),  # 1 year
    }

    if not from_date or not to_date:
        to_datetimes = [datetime.now(tz=timezone.utc)]
        from_datetimes = [to_datetimes[0] - interval2timedelta[interval]]
        return (from_datetimes, to_datetimes)

    try:
        from_datetimes = [datetime.strptime(from_date, Config.date_format)]
        to_datetimes = [datetime.strptime(to_date, Config.date_format)]
    except ValueError:
        from_datetimes = [
            datetime.strptime(from_date, Config.time_format).astimezone(tz=timezone.utc)
        ]
        to_datetimes = [
            datetime.strptime(to_date, Config.time_format).astimezone(tz=timezone.utc)
        ]
    except Exception:
        raise ValueError(
            f"Only supported date formats are `{Config.date_format}` and"
            f" `{Config.time_format}`."
        )

    if from_datetimes[0] > to_datetimes[0]:
        raise ValueError("`from_date` cannot be greater than `to_date`")

    if interval in [
        "W",
        "M",
    ]:  # There are no data retrieval limits for weekly and monthly intervals
        return (from_datetimes, to_datetimes)

    if interval not in [1, 5, 15, 30, "D"]:
        logging.warning(
            "Interval calculation just implemented for 1, 5, 15, 30, 'D' intervals,"
            f" not for {interval}, wait for its implementation."
        )
        return (from_datetimes, to_datetimes)

    interval2limit = {
        1: timedelta(days=13),  # round(5000 / 390) = 13 days (round to half a month)
        5: timedelta(days=64),  # round(5000 / 78) = 64 days (round to two months)
        15: timedelta(days=192),  # round(5000 / 26) = 192 days (round to six months)
        30: timedelta(days=384),  # round(5000 / 13) = 384 days (round to one year)
        "D": timedelta(
            days=6940
        ),  # round(365.25 * 19) = 6940 days (5000 days + bank holidays, weekends, etc.)
    }

    interval2increment = {
        1: timedelta(minutes=1),
        5: timedelta(minutes=5),
        15: timedelta(minutes=15),
        30: timedelta(minutes=30),
        "D": timedelta(days=1),
    }

    if interval != "D":
        no_more_than = {
            1: timedelta(days=182.5),
            5: timedelta(days=258.5),
            15: timedelta(days=457.5),
            30: timedelta(days=661.5),
        }

        if (
            datetime.now(tz=timezone.utc)
            - (from_datetimes[0] + interval2limit[interval])
            > no_more_than[interval]  # type: ignore
        ):
            raise ValueError(
                "Interval between `from_date` and `to_date` cannot be greater than"
                f" {no_more_than[interval].days} days."  # type: ignore
            )

        if datetime.now(tz=timezone.utc) - from_datetimes[0] > no_more_than[interval]:  # type: ignore
            logging.warning(
                "Note that even though the `from_date` parameter is more than"
                f" {no_more_than[interval].days} days ago, due to Investing.com"  # type: ignore
                f" limitations, just the last {no_more_than[interval].days} days of"  # type: ignore
                " data will be retrieved."
            )

    if to_datetimes[0] - from_datetimes[0] > interval2limit[interval]:
        max_to_datetime = to_datetimes[0]
        to_datetimes = [from_datetimes[0] + interval2limit[interval]]
        while max_to_datetime - to_datetimes[-1] > interval2limit[interval]:
            from_datetimes.append(to_datetimes[-1] + interval2increment[interval])
            to_datetimes.append(from_datetimes[-1] + interval2limit[interval])
        if to_datetimes[-1] != max_to_datetime:
            from_datetimes.append(to_datetimes[-1] + interval2increment[interval])
            to_datetimes.append(max_to_datetime)

    return (from_datetimes, to_datetimes)
