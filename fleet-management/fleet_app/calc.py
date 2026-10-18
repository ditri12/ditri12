"""חישובים טהורים: ממוצע נסועה, תחזית טיפול, צפי נסועה שנתית, תוקף טסט/ביטוח.

כל התאריכים הם מחרוזות ISO (YYYY-MM-DD) או אובייקטי date.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional


# ---------- תאריכים ----------

def to_date(v) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    s = str(v)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def days_between(a, b) -> int:
    return (to_date(b) - to_date(a)).days


def add_days(d, n: float) -> date:
    return to_date(d) + timedelta(days=round(n))


def add_months(d, n: int) -> date:
    d = to_date(d)
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last))


def fmt_km(n) -> str:
    return "—" if n is None else f"{int(round(n)):,}"


def fmt_date(d) -> str:
    d = to_date(d)
    return "—" if d is None else d.strftime("%d/%m/%Y")


# ---------- ציר זמן של קילומטראז׳ ----------

@dataclass(order=True)
class Point:
    date: date
    km: int


def build_timeline(readings: Iterable = (), services: Iterable = (), repairs: Iterable = ()) -> list[Point]:
    """מאחד כל תצפית קילומטראז׳ (קריאות, טיפולים, תיקונים) לרשימה ממוינת. לאותו יום נשמר הערך הגבוה."""
    by_date: dict[date, int] = {}

    def push(dv, km):
        d = to_date(dv)
        if d is None or km is None:
            return
        try:
            k = int(km)
        except (TypeError, ValueError):
            return
        if k < 0:
            return
        if d not in by_date or by_date[d] < k:
            by_date[d] = k

    for r in readings:
        push(r["reading_date"], r["km"])
    for s in services:
        push(s["service_date"], s["odometer_km"])
    for r in repairs:
        push(r["repair_date"], r["odometer_km"])
    return [Point(d, k) for d, k in sorted(by_date.items())]


def average_daily_km(timeline: list[Point], window_days: int = 365) -> Optional[float]:
    """ק״מ ליום בממוצע: מהנקודה האחרונה אחורה עד הנקודה המוקדמת ביותר בתוך חלון של שנה.
    אם בחלון יש רק נקודה אחת משתמשים בנקודה שלפניה."""
    if len(timeline) < 2:
        return None
    last = timeline[-1]
    window_start = last.date - timedelta(days=window_days)
    base = next((p for p in timeline if p.date >= window_start), None)
    if base is None or base is last:
        base = timeline[-2]
    days = (last.date - base.date).days
    if days <= 0:
        return None
    return max(0.0, (last.km - base.km) / days)


def km_at(timeline: list[Point], when, rate: Optional[float]) -> Optional[float]:
    """קילומטראז׳ משוער בתאריך נתון: אינטרפולציה בתוך הציר, אקסטרפולציה לפי הקצב מחוצה לו."""
    if not timeline:
        return None
    d = to_date(when)
    first, last = timeline[0], timeline[-1]
    if d >= last.date:
        if d == last.date or rate is None:
            return float(last.km)
        return last.km + rate * (d - last.date).days
    if d <= first.date:
        if d == first.date or rate is None:
            return float(first.km)
        return max(0.0, first.km - rate * (first.date - d).days)
    for a, b in zip(timeline, timeline[1:]):
        if a.date <= d <= b.date:
            span = (b.date - a.date).days
            if span == 0:
                return float(b.km)
            return a.km + (b.km - a.km) * ((d - a.date).days / span)
    return float(last.km)


# ---------- הגדרות ----------

@dataclass
class Settings:
    service_interval_km: int = 15000
    service_interval_months: int = 12
    annual_km_limit: int = 35000
    alert_days: int = 30
    alert_km: int = 1000

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        s = cls()
        for k in s.__dataclass_fields__:
            if k in d and d[k] not in (None, ""):
                setattr(s, k, int(float(d[k])))
        return s

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# ---------- תחזית טיפול ----------

@dataclass
class ServiceForecast:
    status: str = "unknown"            # ok / soon / overdue / unknown
    reason: Optional[str] = None       # 'km' או 'date' - מה מגיע קודם
    expected_date: Optional[date] = None
    days_left: Optional[int] = None
    due_date: Optional[date] = None
    due_km: Optional[int] = None
    km_remaining: Optional[int] = None
    predicted_km_date: Optional[date] = None
    last_service_date: Optional[date] = None
    last_service_km: Optional[int] = None
    message: str = ""


def service_forecast(last_service, timeline: list[Point], today, rate: Optional[float], settings: Settings) -> ServiceForecast:
    """טיפול כל X ק״מ או Y חודשים מהטיפול האחרון - המוקדם מביניהם."""
    if not last_service or not to_date(last_service["service_date"]):
        return ServiceForecast(status="unknown", message="לא הוזן טיפול אחרון")
    t = to_date(today)
    last_date = to_date(last_service["service_date"])
    last_km = last_service.get("odometer_km")
    has_km = last_km is not None and int(last_km) >= 0
    due_date = add_months(last_date, settings.service_interval_months)
    due_km = int(last_km) + settings.service_interval_km if has_km else None

    km_now = km_at(timeline, t, rate) if timeline else None
    km_remaining = (due_km - km_now) if (due_km is not None and km_now is not None) else None

    predicted = None
    if km_remaining is not None:
        if km_remaining <= 0:
            last_point = timeline[-1]
            if last_point.km >= due_km:
                predicted = next(p for p in timeline if p.km >= due_km).date
            elif rate and rate > 0:
                predicted = add_days(last_point.date, (due_km - last_point.km) / rate)
            else:
                predicted = t
        elif rate and rate > 0:
            predicted = add_days(t, km_remaining / rate)

    expected, reason = due_date, "date"
    if predicted and predicted < due_date:
        expected, reason = predicted, "km"
    days_left = (expected - t).days

    status = "ok"
    if days_left < 0 or (km_remaining is not None and km_remaining <= 0):
        status = "overdue"
    elif days_left <= settings.alert_days or (km_remaining is not None and km_remaining <= settings.alert_km):
        status = "soon"

    return ServiceForecast(
        status=status, reason=reason, expected_date=expected, days_left=days_left,
        due_date=due_date, due_km=due_km,
        km_remaining=int(round(km_remaining)) if km_remaining is not None else None,
        predicted_km_date=predicted, last_service_date=last_date,
        last_service_km=int(last_km) if has_km else None,
    )


# ---------- צפי נסועה שנתית ----------

def year_window(today, anchor=None) -> tuple[date, date]:
    """שנת הנסועה: ברירת מחדל שנה קלנדרית; עם anchor (למשל תחילת ליסינג) - מהיום-שנה האחרון של התאריך."""
    t = to_date(today)
    if anchor and to_date(anchor):
        a = to_date(anchor)
        day = min(a.day, calendar.monthrange(t.year, a.month)[1])
        start = date(t.year, a.month, day)
        if start > t:
            day = min(a.day, calendar.monthrange(t.year - 1, a.month)[1])
            start = date(t.year - 1, a.month, day)
        return start, add_months(start, 12)
    return date(t.year, 1, 1), date(t.year + 1, 1, 1)


@dataclass
class MileageProjection:
    status: str = "unknown"            # ok / pace / over / unknown
    year_start: Optional[date] = None
    year_end: Optional[date] = None
    tracked_from: Optional[date] = None
    partial_year: bool = False
    km_now: Optional[int] = None
    driven_so_far: Optional[int] = None
    projected_year_km: Optional[int] = None
    annualized_km: Optional[int] = None
    limit: int = 0
    over_by: Optional[int] = None
    message: str = ""


def annual_projection(timeline: list[Point], today, rate: Optional[float], anchor, settings: Settings) -> MileageProjection:
    limit = settings.annual_km_limit
    if not timeline:
        return MileageProjection(status="unknown", limit=limit, message="לא הוזן קילומטראז׳")
    t = to_date(today)
    start, end = year_window(t, anchor)
    first = timeline[0]
    tracked_from = first.date if first.date > start else start
    partial = first.date > start

    km_now = km_at(timeline, t, rate)
    km_start = km_at(timeline, tracked_from, rate)
    driven = max(0.0, km_now - km_start)
    days_remaining = max(0, (end - t).days)
    days_so_far = max(0, (t - tracked_from).days)

    eff_rate = rate if rate is not None else (driven / days_so_far if days_so_far > 0 else None)
    projected = driven + eff_rate * days_remaining if eff_rate is not None else None
    annualized = eff_rate * 365 if eff_rate is not None else None

    if projected is None:
        status = "unknown"
    elif projected > limit:
        status = "over"
    elif annualized > limit:
        status = "pace"
    else:
        status = "ok"

    return MileageProjection(
        status=status, year_start=start, year_end=end, tracked_from=tracked_from, partial_year=partial,
        km_now=int(round(km_now)), driven_so_far=int(round(driven)),
        projected_year_km=int(round(projected)) if projected is not None else None,
        annualized_km=int(round(annualized)) if annualized is not None else None,
        limit=limit, over_by=int(round(projected - limit)) if projected is not None else None,
    )


# ---------- טסט / ביטוח ----------

@dataclass
class Expiry:
    status: str = "unknown"   # ok / soon / expired / unknown
    days_left: Optional[int] = None
    date: Optional[date] = None


def expiry_status(d, today, alert_days: int) -> Expiry:
    dd = to_date(d)
    if dd is None:
        return Expiry()
    days_left = (dd - to_date(today)).days
    status = "expired" if days_left < 0 else "soon" if days_left <= alert_days else "ok"
    return Expiry(status=status, days_left=days_left, date=dd)


# ---------- סיכום לרכב ----------

@dataclass
class Alert:
    level: str   # danger / warn / info
    type: str    # test / insurance / service / mileage
    text: str


@dataclass
class VehicleStatus:
    today: date
    timeline: list = field(default_factory=list)
    avg_daily_km: Optional[float] = None
    avg_monthly_km: Optional[int] = None
    current_km: Optional[int] = None
    last_point: Optional[Point] = None
    service: ServiceForecast = field(default_factory=ServiceForecast)
    mileage: MileageProjection = field(default_factory=MileageProjection)
    test: Expiry = field(default_factory=Expiry)
    insurance: Expiry = field(default_factory=Expiry)
    alerts: list = field(default_factory=list)

    @property
    def worst_level(self) -> str:
        levels = {a.level for a in self.alerts}
        if "danger" in levels:
            return "danger"
        if "warn" in levels:
            return "warn"
        if "info" in levels:
            return "info"
        return "ok"


def compute_vehicle(vehicle: dict, readings, services, repairs, settings: Settings, today=None) -> VehicleStatus:
    t = to_date(today) or date.today()
    timeline = build_timeline(readings, services, repairs)
    rate = average_daily_km(timeline)
    last_service = max(services, key=lambda s: (s["service_date"], s.get("id", 0)), default=None) if services else None
    last_point = timeline[-1] if timeline else None

    service = service_forecast(last_service, timeline, t, rate, settings)
    mileage = annual_projection(timeline, t, rate, vehicle.get("mileage_year_start"), settings)
    test = expiry_status(vehicle.get("test_expiry"), t, settings.alert_days)
    insurance = expiry_status(vehicle.get("insurance_expiry"), t, settings.alert_days)

    alerts: list[Alert] = []
    if test.status == "expired":
        alerts.append(Alert("danger", "test", f"הטסט פג לפני {-test.days_left} ימים"))
    elif test.status == "soon":
        alerts.append(Alert("warn", "test", f"הטסט פג בעוד {test.days_left} ימים"))
    if insurance.status == "expired":
        alerts.append(Alert("danger", "insurance", f"הביטוח פג לפני {-insurance.days_left} ימים"))
    elif insurance.status == "soon":
        alerts.append(Alert("warn", "insurance", f"הביטוח פג בעוד {insurance.days_left} ימים"))
    if service.status == "overdue":
        alerts.append(Alert("danger", "service", "הרכב באיחור לטיפול"))
    elif service.status == "soon":
        alerts.append(Alert("warn", "service", f"טיפול צפוי בעוד {service.days_left} ימים"))
    elif service.status == "unknown":
        alerts.append(Alert("info", "service", "לא הוזן טיפול אחרון"))
    if mileage.status == "over":
        alerts.append(Alert("danger", "mileage", f"צפי נסועה שנתית {fmt_km(mileage.projected_year_km)} ק״מ - מעל המכסה ({fmt_km(settings.annual_km_limit)})"))
    elif mileage.status == "pace":
        alerts.append(Alert("warn", "mileage", f"קצב הנסיעה ({fmt_km(mileage.annualized_km)} ק״מ/שנה) גבוה מהמכסה"))
    elif mileage.status == "unknown":
        alerts.append(Alert("info", "mileage", "לא הוזן קילומטראז׳"))

    return VehicleStatus(
        today=t, timeline=timeline,
        avg_daily_km=round(rate, 1) if rate is not None else None,
        avg_monthly_km=int(round(rate * 30.44)) if rate is not None else None,
        current_km=int(round(km_at(timeline, t, rate))) if last_point else None,
        last_point=last_point, service=service, mileage=mileage, test=test, insurance=insurance, alerts=alerts,
    )
