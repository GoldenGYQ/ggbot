from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .context import ToolContext
from .registry import tool


class GetCurrentTimeArgs(BaseModel):
    """Arguments for getting current time."""
    timezone: str | None = Field(
        None,
        description="Optional timezone name (e.g., 'UTC', 'Asia/Shanghai', 'America/New_York'). "
                    "If not provided, uses local system time.",
    )
    format: str | None = Field(
        None,
        description="Optional datetime format string. Default: ISO 8601 format. "
                    "Examples: '%Y-%m-%d %H:%M:%S', '%A, %B %d, %Y %I:%M %p'",
    )


class GetDateInfoArgs(BaseModel):
    """Arguments for getting detailed date information."""
    date: str | None = Field(
        None,
        description="Optional date string in ISO format (YYYY-MM-DD). "
                    "If not provided, uses current date.",
    )
    timezone: str | None = Field(
        None,
        description="Optional timezone name. If not provided, uses local system timezone.",
    )


class GetTimezoneListArgs(BaseModel):
    """Arguments for getting timezone list (no parameters needed)."""
    pass


def make_time_tools():
    @tool()
    def get_current_time(ctx: ToolContext, args: GetCurrentTimeArgs) -> dict[str, Any]:
        """Get current date and time with optional timezone and formatting."""

        try:
            if args.timezone:
                # Try to get timezone
                import pytz
                tz = pytz.timezone(args.timezone)
                now = datetime.now(tz)
            else:
                # Local system time
                now = datetime.now()

            if args.format:
                formatted = now.strftime(args.format)
            else:
                formatted = now.isoformat()

            return {
                "timestamp": now.timestamp(),
                "iso_format": now.isoformat(),
                "formatted": formatted,
                "timezone": str(now.tzinfo) if now.tzinfo else "local",
                "utc_offset": now.utcoffset().total_seconds() / 3600 if now.utcoffset() else None,
                "components": {
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                    "microsecond": now.microsecond,
                    "weekday": now.strftime("%A"),
                    "weekday_number": now.weekday(),  # 0=Monday, 6=Sunday
                    "isoweekday": now.isoweekday(),  # 1=Monday, 7=Sunday
                }
            }

        except Exception as e:
            # Fallback to simple time if pytz not available or timezone invalid
            now = datetime.now()
            if args.format:
                formatted = now.strftime(args.format)
            else:
                formatted = now.isoformat()

            return {
                "timestamp": now.timestamp(),
                "iso_format": now.isoformat(),
                "formatted": formatted,
                "timezone": "local",
                "utc_offset": None,
                "components": {
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                    "microsecond": now.microsecond,
                    "weekday": now.strftime("%A"),
                    "weekday_number": now.weekday(),
                    "isoweekday": now.isoweekday(),
                },
                "warning": f"Using local time (timezone error: {str(e)})"
            }

    @tool()
    def get_date_info(ctx: ToolContext, args: GetDateInfoArgs) -> dict[str, Any]:
        """Get detailed information about a specific date."""

        from datetime import date as date_type

        try:
            if args.date:
                target_date = date_type.fromisoformat(args.date)
            else:
                target_date = date_type.today()

            # Calculate various date properties
            import calendar

            # Get month calendar
            cal = calendar.monthcalendar(target_date.year, target_date.month)

            # Calculate day of year
            day_of_year = target_date.timetuple().tm_yday

            # Calculate week number (ISO week)
            iso_year, iso_week, iso_weekday = target_date.isocalendar()

            # Check if it's a weekend
            is_weekend = target_date.weekday() >= 5  # 5=Saturday, 6=Sunday

            # Check if it's a holiday (basic check for common holidays)
            holidays = []
            if target_date.month == 1 and target_date.day == 1:
                holidays.append("New Year's Day")
            elif target_date.month == 12 and target_date.day == 25:
                holidays.append("Christmas Day")

            # Days until end of month
            import calendar
            _, last_day = calendar.monthrange(target_date.year, target_date.month)
            days_until_month_end = last_day - target_date.day

            # Days until end of year
            days_until_year_end = (date_type(target_date.year, 12, 31) - target_date).days

            return {
                "date": target_date.isoformat(),
                "year": target_date.year,
                "month": target_date.month,
                "month_name": target_date.strftime("%B"),
                "day": target_date.day,
                "day_name": target_date.strftime("%A"),
                "weekday_number": target_date.weekday(),  # 0=Monday
                "is_weekend": is_weekend,
                "day_of_year": day_of_year,
                "iso_year": iso_year,
                "iso_week": iso_week,
                "iso_weekday": iso_weekday,
                "quarter": (target_date.month - 1) // 3 + 1,
                "is_leap_year": calendar.isleap(target_date.year),
                "days_in_month": last_day,
                "days_until_month_end": days_until_month_end,
                "days_until_year_end": days_until_year_end,
                "holidays": holidays,
                "calendar_week": cal,
            }

        except ValueError as e:
            return {
                "error": f"Invalid date format: {str(e)}",
                "expected_format": "YYYY-MM-DD",
                "example": "2024-12-25"
            }

    @tool()
    def get_timezone_list(ctx: ToolContext, args: GetTimezoneListArgs) -> dict[str, Any]:
        """Get list of common timezones."""

        common_timezones = [
            "UTC",
            "GMT",
            "EST", "EDT", "CST", "CDT", "MST", "MDT", "PST", "PDT",  # US timezones
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Europe/Moscow",
            "Asia/Shanghai",
            "Asia/Tokyo",
            "Asia/Seoul",
            "Asia/Singapore",
            "Asia/Kolkata",
            "Australia/Sydney",
            "Australia/Melbourne",
            "Pacific/Auckland",
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
            "America/Toronto",
            "America/Vancouver",
        ]

        # Try to get full list from pytz if available
        try:
            import pytz
            all_timezones = pytz.all_timezones
            return {
                "common_timezones": common_timezones,
                "all_timezones_count": len(all_timezones),
                "note": "Install 'pytz' package for full timezone support"
            }
        except ImportError:
            return {
                "common_timezones": common_timezones,
                "note": "Install 'pytz' package for full timezone support. Using common timezones only."
            }

    return get_current_time, get_date_info, get_timezone_list