"""The one filter slice every metric is computed against.

The dashboard has a single filter row above all three sections, so every query
takes the same window and the same CI dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import ColumnElement
from sqlalchemy.sql.elements import BooleanClauseList

from ..persistence.tables import TestRun


@dataclass(frozen=True)
class Slice:
    days: int = 14
    application_code: str | None = None
    region: str | None = None
    environment: str | None = None

    @property
    def start_date(self) -> date:
        return date.today() - timedelta(days=self.days - 1)

    def run_conditions(self) -> list[ColumnElement[bool] | BooleanClauseList]:
        conditions: list[ColumnElement[bool] | BooleanClauseList] = [
            TestRun.run_date >= self.start_date
        ]
        if self.application_code:
            conditions.append(TestRun.application_code == self.application_code)
        if self.region:
            conditions.append(TestRun.region == self.region)
        if self.environment:
            conditions.append(TestRun.environment == self.environment)
        return conditions
