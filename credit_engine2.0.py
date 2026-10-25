from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import random
import sys
import unittest
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 40
D = Decimal

SCHEMA_VERSION = "1.0"
ENGINE_VERSION = "scorecard-demo-v1"
POLICY_VERSION = "policy-demo-v1"
POLICY = {
    "base_rate": D("0.20"),              
    "rate_step_per_point": D("0.001"),    
    "dscr_min": D("1.3"),                 
    "dscr_min_strict": D("1.6"),          
    "amount_step_rub": 1000,
    "band_low_from": 75,                  
    "band_medium_from": 50,
    "severe_overdue_days": 90,
    "products": {
        "working_capital": {
            "title": "Оборотные средства", "min_age_months": 12,
            "min_amount_rub": 100_000, "max_amount_rub": 3_000_000,
            "min_term_months": 6, "max_term_months": 24, "margin": D("0.04"),
        },
        "equipment": {
            "title": "Оборудование", "min_age_months": 24,
            "min_amount_rub": 300_000, "max_amount_rub": 5_000_000,
            "min_term_months": 12, "max_term_months": 36, "margin": D("0.02"),
        },
    },
}

FIN_FIELDS = (
    "monthly_revenue_rub",
    "monthly_cash_available_for_debt_service_rub",
    "existing_monthly_debt_service_rub",
    "revenue_cv_12m",
    "largest_customer_share",
)
CHECK_VALUES = {
    "registry": ("active", "inactive", "unavailable"),
    "authority": ("verified", "unverified", "unavailable"),
    "credit_history": ("available", "no_history", "unavailable"),
    "fraud": ("clear", "flagged", "unavailable"),
}
TOP_FIELDS = (
    "application_id", "revision", "product_id", "requested_amount_rub",
    "requested_term_months", "company", "financials", "checks", "credit_report_consent_valid",
)

DECISIONS = ("APPROVED", "COUNTEROFFER", "NEED_INFO", "MANUAL_REVIEW", "DECLINED")
STATUS_MAP = {
    "APPROVED": "OFFER_MADE",
    "COUNTEROFFER": "OFFER_MADE",
    "NEED_INFO": "NEEDS_INFO",
    "MANUAL_REVIEW": "MANUAL_REVIEW",
    "DECLINED": "REJECTED",
}
NEXT_ACTION = {
    "APPROVED": "ACCEPT_OR_DECLINE_OFFER",
    "COUNTEROFFER": "ACCEPT_OR_DECLINE_OFFER",
    "NEED_INFO": "PROVIDE_INFORMATION",
    "MANUAL_REVIEW": "WAIT_FOR_REVIEW",
    "DECLINED": "VIEW_RESULT",
}

REASON_TEXT_RU = {
    "MISSING_REQUIRED_INFORMATION": "Не хватает данных или согласия на запрос кредитного отчёта, дополните заявку.",
    "BUSINESS_INACTIVE": "По данным реестра бизнес не является действующим.",
    "AUTHORITY_NOT_VERIFIED": "Не удалось подтвердить полномочия заявителя.",
    "CHECKS_REQUIRE_REVIEW": "Одну из проверок не удалось завершить автоматически.",
    "CHECKS_NOT_PASSED": "Заявка не прошла внутренние проверки.",
    "NO_CREDIT_HISTORY": "У компании нет кредитной истории.",
    "SEVERE_DELINQUENCY": "За последние 12 месяцев есть просрочка от 90 дней.",
    "HIGH_DEMO_RISK": "Оценка риска ниже допустимой для автоматического решения.",
    "MEDIUM_DEMO_RISK": "Оценка риска средняя, решение требует дополнительного рассмотрения.",
    "PRODUCT_BUSINESS_AGE_REQUIREMENT": "Бизнес младше минимального возраста для этого продукта. Попробуйте другой продукт.",
    "INSUFFICIENT_CASH_FLOW": "Доступный денежный поток не позволяет обслуживать кредит.",
    "NO_AFFORDABLE_OFFER": "Подходящих условий в пределах вашей платёжеспособности нет.",
    "TERM_CHANGED_TO_PRODUCT_RANGE": "Срок приведён к допустимому для продукта.",
    "AMOUNT_LIMITED_BY_PRODUCT_OR_AFFORDABILITY": "Сумма ограничена лимитом продукта или платёжеспособностью.",
    "DEMO_POLICY_PASSED": "Заявка одобрена на запрошенных условиях.",
    "STRICTER_AFFORDABILITY": "Применён более строгий порог платёжеспособности.",
}


class RequestError(ValueError):
    """Technically invalid request (backend should answer HTTP 422, not a credit decline)."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


InvalidRequest = RequestError  

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check_keys(obj, path, errs, required=(), allowed=()):
    if not isinstance(obj, dict):
        errs.append(f"{path}: must be an object")
        return False
    for k in required:
        if k not in obj:
            errs.append(f"{path}.{k}: required")
    ok = set(required) | set(allowed)
    for k in obj:
        if k not in ok:
            errs.append(f"{path}.{k}: unknown field")
    return True


def validate_request(request):
    """Strict structural validation: no nulls, no extra fields, no bools as numbers, no NaN/Inf."""
    errs = []
    if not isinstance(request, dict):
        raise RequestError(["$: request must be a JSON object"])
    _check_keys(request, "$", errs, required=TOP_FIELDS)

    v = request.get("application_id")
    if "application_id" in request and not (isinstance(v, str) and 1 <= len(v) <= 100):
        errs.append("$.application_id: non-empty string up to 100 chars")
    v = request.get("revision")
    if "revision" in request and not (_is_int(v) and 1 <= v <= 10**12):
        errs.append("$.revision: integer 1..1e12")
    v = request.get("product_id")
    if "product_id" in request and not (isinstance(v, str) and v in POLICY["products"]):
        errs.append(f"$.product_id: one of {sorted(POLICY['products'])}")
    v = request.get("requested_amount_rub")
    if "requested_amount_rub" in request and not (_is_int(v) and 1 <= v <= 1_000_000_000):
        errs.append("$.requested_amount_rub: integer 1..1e9")
    v = request.get("requested_term_months")
    if "requested_term_months" in request and not (_is_int(v) and 1 <= v <= 120):
        errs.append("$.requested_term_months: integer 1..120")
    v = request.get("credit_report_consent_valid")
    if "credit_report_consent_valid" in request and not isinstance(v, bool):
        errs.append("$.credit_report_consent_valid: boolean")

    if "company" in request and _check_keys(request["company"], "$.company", errs, required=("age_months",)):
        v = request["company"].get("age_months")
        if "age_months" in request["company"] and not (_is_int(v) and 0 <= v <= 1200):
            errs.append("$.company.age_months: integer 0..1200")

    if "financials" in request and _check_keys(request["financials"], "$.financials", errs, allowed=FIN_FIELDS):
        f = request["financials"]
        rules = {
            "monthly_revenue_rub": (lambda x: 1 <= x <= 1e12, "number 1..1e12"),
            "monthly_cash_available_for_debt_service_rub": (lambda x: -1e12 <= x <= 1e12, "number -1e12..1e12"),
            "existing_monthly_debt_service_rub": (lambda x: 0 <= x <= 1e12, "number 0..1e12"),
            "revenue_cv_12m": (lambda x: 0 <= x <= 10, "number 0..10"),
            "largest_customer_share": (lambda x: 0 <= x <= 1, "number 0..1"),
        }
        for k, (pred, text) in rules.items():
            if k in f and not (_is_num(f[k]) and pred(f[k])):
                errs.append(f"$.financials.{k}: {text}")

    if "checks" in request and _check_keys(
        request["checks"], "$.checks", errs, required=tuple(CHECK_VALUES) + ("max_overdue_days_12m",)
    ):
        c = request["checks"]
        for k, allowed in CHECK_VALUES.items():
            if k in c and c[k] not in allowed:
                errs.append(f"$.checks.{k}: one of {list(allowed)}")
        v = c.get("max_overdue_days_12m")
        if "max_overdue_days_12m" in c and not (_is_int(v) and 0 <= v <= 366):
            errs.append("$.checks.max_overdue_days_12m: integer 0..366")

    if errs:
        raise RequestError(errs)

def _dec(x):
    return D(str(x))


def _payment_factor(annual_rate, term_months):
    r = D(annual_rate) / 12
    return r / (1 - (1 + r) ** (-term_months))


def annuity_payment(principal, annual_rate, term_months):
    """Annuity payment, rounded UP to kopecks. No calendar schedule, no APR (demo formula)."""
    raw = D(principal) * _payment_factor(annual_rate, term_months)
    raw = raw.quantize(D("1e-12"), rounding=ROUND_HALF_UP)  # kill representation noise
    return raw.quantize(D("0.01"), rounding=ROUND_CEILING)


def _rate_for(product, score):
    p = POLICY["products"][product]
    return POLICY["base_rate"] + p["margin"] + POLICY["rate_step_per_point"] * (100 - score)

def compute_risk(company, financials, checks):
    """Return {score 0..100, scale, band LOW/MEDIUM/HIGH, factors[{code, points<0}], calibrated_pd=None}.

    Penalties of different factors add up; inside one factor only the strongest applies.
    The overdue factor is used only when the credit history is available (no history is
    NOT the same as 'no overdue')."""
    pens = []
    age = company["age_months"]
    if age < 12:
        pens.append(("SHORT_BUSINESS_HISTORY", 20))
    elif age < 24:
        pens.append(("SHORT_BUSINESS_HISTORY", 10))

    cash = _dec(financials["monthly_cash_available_for_debt_service_rub"])
    rev = _dec(financials["monthly_revenue_rub"])
    ratio = cash / rev
    if ratio <= 0:
        pens.append(("LOW_CASH_MARGIN", 30))
    elif ratio < D("0.10"):
        pens.append(("LOW_CASH_MARGIN", 20))
    elif ratio < D("0.20"):
        pens.append(("LOW_CASH_MARGIN", 10))

    cv = _dec(financials["revenue_cv_12m"])
    if cv > D("0.5"):
        pens.append(("REVENUE_VOLATILITY", 15))
    elif cv > D("0.25"):
        pens.append(("REVENUE_VOLATILITY", 5))

    if _dec(financials["largest_customer_share"]) > D("0.5"):
        pens.append(("CLIENT_CONCENTRATION", 10))

    if checks["credit_history"] == "available":
        od = checks["max_overdue_days_12m"]
        if od >= 30:
            pens.append(("DELINQUENCY_HISTORY", 25))
        elif od >= 1:
            pens.append(("DELINQUENCY_HISTORY", 10))

    debt = _dec(financials["existing_monthly_debt_service_rub"])
    if cash <= 0 or debt > cash * D("0.5"):
        pens.append(("EXISTING_DEBT_BURDEN", 20))

    score = max(0, 100 - sum(p for _, p in pens))
    if score >= POLICY["band_low_from"]:
        band = "LOW"
    elif score >= POLICY["band_medium_from"]:
        band = "MEDIUM"
    else:
        band = "HIGH"
    return {
        "score": score,
        "scale": "0..100; higher is better",
        "band": band,
        "factors": [{"code": c, "points": -p} for c, p in pens],
        "calibrated_pd": None,  # the model is not trained or calibrated, never fake it
    }

def _find_offer(product_id, req_amount, req_term, score, cash, existing, dscr_min):
    prod = POLICY["products"][product_id]
    step = POLICY["amount_step_rub"]
    term = min(max(req_term, prod["min_term_months"]), prod["max_term_months"])
    rate = _rate_for(product_id, score)
    cash, existing = _dec(cash), _dec(existing)
    if cash <= 0:
        return None
    max_payment = cash / dscr_min - existing
    if max_payment <= 0:
        return None
    cap = min(req_amount, prod["max_amount_rub"]) // step * step
    by_cash = int((max_payment / _payment_factor(rate, term)) // step * step)
    amount = min(cap, by_cash)
    while amount >= prod["min_amount_rub"]:
        pay = annuity_payment(amount, rate, term)
        dscr = cash / (existing + pay)
        if dscr >= dscr_min:
            return {
                "product_id": product_id,
                "amount_rub": int(amount),
                "term_months": term,
                "annual_rate": float(rate),
                "monthly_payment_rub": float(pay),
                "dscr": float(dscr.quantize(D("0.000001"), rounding=ROUND_HALF_UP)),
                "repayment_type": "ANNUITY",
                "fees_rub": 0,
                "insurance_rub": 0,
                "collateral_required": False,
            }
        amount -= step  
    return None

def _result(req, decision, *, risk=None, offer=None, reasons=(), missing=(), next_action=None):
    return {
        "application_id": req["application_id"],
        "revision": req["revision"],
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "policy_version": POLICY_VERSION,
        "demo": True,
        "decision": decision,
        "risk": risk,
        "offer": offer,
        "reason_codes": list(reasons),
        "missing_fields": list(missing),
        "next_action": next_action or NEXT_ACTION[decision],
    }


def _gate(checks):
    """First check that needs a human (same priority as the team's engine.py), else None."""
    if checks["authority"] != "verified":
        return "AUTHORITY_NOT_VERIFIED"
    if checks["registry"] == "unavailable" or checks["credit_history"] == "unavailable" or checks["fraud"] != "clear":
        return "CHECKS_REQUIRE_REVIEW"
    if checks["credit_history"] == "no_history":
        return "NO_CREDIT_HISTORY"
    return None


def _decide_scored(req, risk, *, manual_allowed, strict=False, extra=()):
    prod = POLICY["products"][req["product_id"]]
    band = risk["band"]
    extra = list(extra)
    if band == "HIGH":
        return _result(req, "DECLINED", risk=risk, reasons=extra + ["HIGH_DEMO_RISK"])
    if req["company"]["age_months"] < prod["min_age_months"]:
        return _result(req, "DECLINED", risk=risk, reasons=extra + ["PRODUCT_BUSINESS_AGE_REQUIREMENT"],
                       next_action="CHANGE_PRODUCT")
    if band == "MEDIUM" and manual_allowed:
        return _result(req, "MANUAL_REVIEW", risk=risk, reasons=extra + ["MEDIUM_DEMO_RISK"])

    use_strict = strict or band == "MEDIUM"      
    if band == "MEDIUM":
        extra.append("MEDIUM_DEMO_RISK")
    if use_strict:
        extra.append("STRICTER_AFFORDABILITY")
    f = req["financials"]
    if _dec(f["monthly_cash_available_for_debt_service_rub"]) <= 0:
        return _result(req, "DECLINED", risk=risk, reasons=extra + ["INSUFFICIENT_CASH_FLOW"])

    dscr_min = POLICY["dscr_min_strict"] if use_strict else POLICY["dscr_min"]
    offer = _find_offer(
        req["product_id"], req["requested_amount_rub"], req["requested_term_months"], risk["score"],
        f["monthly_cash_available_for_debt_service_rub"], f["existing_monthly_debt_service_rub"], dscr_min,
    )
    if offer is None:
        return _result(req, "DECLINED", risk=risk, reasons=extra + ["NO_AFFORDABLE_OFFER"])

    reasons = []
    if offer["term_months"] != req["requested_term_months"]:
        reasons.append("TERM_CHANGED_TO_PRODUCT_RANGE")
    if offer["amount_rub"] != req["requested_amount_rub"]:
        reasons.append("AMOUNT_LIMITED_BY_PRODUCT_OR_AFFORDABILITY")
    decision = "COUNTEROFFER" if reasons else "APPROVED"
    return _result(req, decision, risk=risk, offer=offer, reasons=extra + (reasons or ["DEMO_POLICY_PASSED"]))


def _auto_resolve(req, gate):
    """No bank staff in the product -> the algorithm closes MANUAL_REVIEW cases itself.
    Demo assumptions (agree them with the team):
      antifraud flag                        -> DECLINED
      authority / source / antifraud issue  -> NEED_INFO (confirm authority or retry later)
      only 'no credit history'              -> score without the overdue factor + stricter DSCR."""
    c = req["checks"]
    if c["fraud"] == "flagged":
        return _result(req, "DECLINED", reasons=["CHECKS_NOT_PASSED"])
    if gate in ("AUTHORITY_NOT_VERIFIED", "CHECKS_REQUIRE_REVIEW"):
        return _result(req, "NEED_INFO", reasons=[gate])
    risk = compute_risk(req["company"], req["financials"], c)
    return _decide_scored(req, risk, manual_allowed=False, strict=True, extra=["NO_CREDIT_HISTORY"])


def evaluate(request, *, staff_review=True):
    """Inference entry point. Pure function: same snapshot + versions -> same result.
    Raises RequestError (= InvalidRequest) for technically invalid input; that is not a credit decline."""
    validate_request(request)
    req = request
    fin, chk = req["financials"], req["checks"]

    missing = [f"financials.{k}" for k in FIN_FIELDS if k not in fin]
    if not req["credit_report_consent_valid"]:
        missing.append("credit_report_consent_valid")
    if missing:
        return _result(req, "NEED_INFO", reasons=["MISSING_REQUIRED_INFORMATION"], missing=missing)

    if chk["registry"] == "inactive":
        return _result(req, "DECLINED", reasons=["BUSINESS_INACTIVE"])

    gate = _gate(chk)
    if gate:
        if staff_review:
            return _result(req, "MANUAL_REVIEW", reasons=[gate])
        return _auto_resolve(req, gate)

    if chk["max_overdue_days_12m"] >= POLICY["severe_overdue_days"]:
        return _result(req, "DECLINED", reasons=["SEVERE_DELINQUENCY"])

    risk = compute_risk(req["company"], fin, chk)
    return _decide_scored(req, risk, manual_allowed=staff_review)

def to_application_status(decision):
    """Inference decision -> status of the application state machine."""
    return STATUS_MAP[decision]


def input_hash(request):
    """Stable sha256 of the request snapshot; store it next to the evaluation."""
    blob = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def public_view(result):
    """Client-safe result: adds Russian texts for reason codes and the application status.
    Antifraud details never reach the result in the first place (codes are generic)."""
    pub = copy.deepcopy(result)
    pub["reasons"] = [{"code": c, "text": REASON_TEXT_RU.get(c, c)} for c in pub["reason_codes"]]
    pub["status"] = to_application_status(pub["decision"])
    return pub


def describe():
    """Engine card for the 'describe' deliverable: what it takes, what it does, what it does NOT claim."""
    return {
        "name": "credit_engine",
        "engine_version": ENGINE_VERSION,
        "policy_version": POLICY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "demo": True,
        "type": "explainable points scorecard + separate credit policy; no ML training",
        "inputs": {
            "application": ["application_id", "revision", "product_id", "requested_amount_rub",
                            "requested_term_months", "credit_report_consent_valid"],
            "company": {"age_months": "business age, not applicant age"},
            "financials": {
                "monthly_revenue_rub": "average monthly revenue, > 0",
                "monthly_cash_available_for_debt_service_rub": "after opex and taxes, before debt service; may be negative",
                "existing_monthly_debt_service_rub": "sum of current monthly debt payments; unknown != 0",
                "revenue_cv_12m": "population std of 12 monthly revenues / mean",
                "largest_customer_share": "0..1",
            },
            "checks": {**{k: list(v) for k, v in CHECK_VALUES.items()},
                       "max_overdue_days_12m": "0..366, ignored when no credit history"},
        },
        "pipeline": [
            "missing financial field or no valid consent -> NEED_INFO",
            "registry inactive -> DECLINED",
            "authority not verified / source unavailable / antifraud not clear / no credit history -> MANUAL_REVIEW",
            "max overdue >= 90 days -> DECLINED",
            "score: LOW 75-100, MEDIUM 50-74, HIGH 0-49",
            "HIGH -> DECLINED; business younger than product minimum -> DECLINED",
            "MEDIUM -> MANUAL_REVIEW; LOW -> offer search",
            "offer search: max amount (step 1000 RUB) <= request and product max with DSCR >= 1.3",
            "same amount and term -> APPROVED; changed -> COUNTEROFFER; nothing >= product min -> DECLINED",
        ],
        "score_penalties": {
            "SHORT_BUSINESS_HISTORY (age <12 / 12-23 months)": "20 / 10",
            "LOW_CASH_MARGIN (cash flow / revenue <=0 / <10% / <20%)": "30 / 20 / 10",
            "REVENUE_VOLATILITY (CV >0.5 / >0.25)": "15 / 5",
            "CLIENT_CONCENTRATION (largest customer >50%)": "10",
            "DELINQUENCY_HISTORY (max overdue 30+ / 1-29 days)": "25 / 10",
            "EXISTING_DEBT_BURDEN (debt service >50% of cash flow, or cash flow <=0)": "20",
        },
        "rate": "20% + product margin (WC 4pp, equipment 2pp) + 0.1pp per score point below 100",
        "products": {k: {kk: (float(vv) if isinstance(vv, D) else vv) for kk, vv in v.items()}
                     for k, v in POLICY["products"].items()},
        "dscr_min": float(POLICY["dscr_min"]),
        "limitations": [
            "synthetic data, hand-set thresholds; the score is not a default predictor",
            "calibrated_pd is always null; no AUC/calibration claims without outcome data",
            "annuity formula only: no calendar schedule, APR, fees, insurance, collateral",
            "does not store applications, create offer_id/expires_at or guard against double disbursement",
            "no authentication; call it only from the trusted backend",
        ],
    }

def _base_request():
    return {
        "application_id": "demo-0001",
        "revision": 1,
        "product_id": "working_capital",
        "requested_amount_rub": 1_000_000,
        "requested_term_months": 24,
        "company": {"age_months": 36},
        "financials": {
            "monthly_revenue_rub": 1_500_000,
            "monthly_cash_available_for_debt_service_rub": 400_000,
            "existing_monthly_debt_service_rub": 50_000,
            "revenue_cv_12m": 0.15,
            "largest_customer_share": 0.25,
        },
        "checks": {"registry": "active", "authority": "verified", "credit_history": "available",
                   "fraud": "clear", "max_overdue_days_12m": 0},
        "credit_report_consent_valid": True,
    }


def example_request(kind="approved"):
    r = _base_request()
    if kind == "approved":
        pass
    elif kind == "counteroffer":
        r["application_id"] = "demo-0002"
        r["requested_amount_rub"] = 3_000_000
        r["financials"].update(monthly_revenue_rub=1_200_000,
                               monthly_cash_available_for_debt_service_rub=150_000,
                               existing_monthly_debt_service_rub=30_000)
    elif kind == "need_info":
        r["application_id"] = "demo-0003"
        del r["financials"]["revenue_cv_12m"]
    elif kind == "manual_review":
        r["application_id"] = "demo-0004"
        r["checks"].update(credit_history="no_history", max_overdue_days_12m=0)
    elif kind == "declined_high":
        r["application_id"] = "demo-0005"
        r["company"]["age_months"] = 14
        r["financials"].update(monthly_cash_available_for_debt_service_rub=-20_000,
                               revenue_cv_12m=0.6, largest_customer_share=0.6)
    elif kind == "declined_overdue":
        r["application_id"] = "demo-0006"
        r["checks"]["max_overdue_days_12m"] = 120
    else:
        raise KeyError(kind)
    return r


EXAMPLE_KINDS = ("approved", "counteroffer", "need_info", "manual_review", "declined_high", "declined_overdue")

class EngineTests(unittest.TestCase):
    def test_reference_example_from_doc(self):
        res = evaluate(example_request("approved"))
        self.assertEqual(res["decision"], "APPROVED")
        self.assertEqual(res["risk"]["score"], 100)
        self.assertEqual(res["risk"]["band"], "LOW")
        self.assertEqual((res["schema_version"], res["engine_version"]), ("1.0", "scorecard-demo-v1"))
        self.assertIsNone(res["risk"]["calibrated_pd"])
        o = res["offer"]
        self.assertEqual(o["annual_rate"], 0.24)
        self.assertEqual(o["monthly_payment_rub"], 52871.10)
        self.assertEqual(o["dscr"], 3.888361)
        self.assertEqual((o["amount_rub"], o["term_months"]), (1_000_000, 24))
        self.assertEqual((res["reason_codes"], res["next_action"]), (["DEMO_POLICY_PASSED"], "ACCEPT_OR_DECLINE_OFFER"))

    def test_five_business_outcomes(self):
        got = {k: evaluate(example_request(k))["decision"] for k in EXAMPLE_KINDS}
        self.assertEqual(got, {
            "approved": "APPROVED", "counteroffer": "COUNTEROFFER", "need_info": "NEED_INFO",
            "manual_review": "MANUAL_REVIEW", "declined_high": "DECLINED", "declined_overdue": "DECLINED",
        })

    def test_counteroffer_is_maximal_and_affordable(self):
        req = example_request("counteroffer")
        o = evaluate(req)["offer"]
        f = req["financials"]
        cash, debt = _dec(f["monthly_cash_available_for_debt_service_rub"]), _dec(f["existing_monthly_debt_service_rub"])
        self.assertEqual(o["amount_rub"] % 1000, 0)
        self.assertLess(o["amount_rub"], req["requested_amount_rub"])
        self.assertGreaterEqual(cash / (debt + _dec(o["monthly_payment_rub"])), D("1.3"))
        nxt = annuity_payment(o["amount_rub"] + 1000, o["annual_rate"], o["term_months"])
        self.assertLess(cash / (debt + nxt), D("1.3"))

    def test_need_info_and_consent(self):
        res = evaluate(example_request("need_info"))
        self.assertEqual(res["missing_fields"], ["financials.revenue_cv_12m"])
        self.assertEqual((res["reason_codes"], res["next_action"]), (["MISSING_REQUIRED_INFORMATION"], "PROVIDE_INFORMATION"))
        r = example_request("approved")
        r["credit_report_consent_valid"] = False
        res = evaluate(r)
        self.assertEqual((res["decision"], res["reason_codes"]), ("NEED_INFO", ["MISSING_REQUIRED_INFORMATION"]))
        self.assertEqual(res["missing_fields"], ["credit_report_consent_valid"])

    def test_check_order_first_reason(self):
        r = example_request("need_info")      # missing field AND flagged fraud
        r["checks"]["fraud"] = "flagged"
        self.assertEqual(evaluate(r)["decision"], "NEED_INFO")
        r = example_request("approved")
        r["checks"]["registry"] = "inactive"
        r["checks"]["fraud"] = "flagged"
        self.assertEqual(evaluate(r)["reason_codes"], ["BUSINESS_INACTIVE"])

    def test_same_risk_different_products(self):
        a = example_request("approved")
        b = copy.deepcopy(a)
        b["product_id"] = "equipment"
        ra, rb = evaluate(a), evaluate(b)
        self.assertEqual(ra["risk"]["score"], rb["risk"]["score"])
        self.assertEqual((ra["offer"]["annual_rate"], rb["offer"]["annual_rate"]), (0.24, 0.22))
        self.assertEqual(rb["decision"], "APPROVED")          # 24 months fits equipment range 12..36
        self.assertEqual(rb["offer"]["term_months"], 24)

    def test_product_age_and_term_range(self):
        r = example_request("approved")
        r["product_id"] = "equipment"
        r["company"]["age_months"] = 18
        res = evaluate(r)
        self.assertEqual((res["decision"], res["reason_codes"]), ("DECLINED", ["PRODUCT_BUSINESS_AGE_REQUIREMENT"]))
        self.assertEqual(res["next_action"], "CHANGE_PRODUCT")
        r = example_request("approved")
        r["requested_term_months"] = 60
        res = evaluate(r)
        self.assertEqual((res["decision"], res["offer"]["term_months"]), ("COUNTEROFFER", 24))
        self.assertIn("TERM_CHANGED_TO_PRODUCT_RANGE", res["reason_codes"])

    def test_no_credit_history_is_not_zero_overdue(self):
        r = example_request("manual_review")
        res = evaluate(r)
        self.assertEqual((res["decision"], res["reason_codes"]), ("MANUAL_REVIEW", ["NO_CREDIT_HISTORY"]))
        self.assertIsNone(res["risk"])
        risk = compute_risk(r["company"], r["financials"], r["checks"])
        self.assertNotIn("DELINQUENCY_HISTORY", [p["code"] for p in risk["factors"]])

    def test_no_staff_mode_resolves_everything(self):
        for kind in EXAMPLE_KINDS:
            res = evaluate(example_request(kind), staff_review=False)
            self.assertNotEqual(res["decision"], "MANUAL_REVIEW", kind)
        r = example_request("manual_review")
        res = evaluate(r, staff_review=False)
        self.assertIn(res["decision"], ("APPROVED", "COUNTEROFFER"))
        self.assertIn("STRICTER_AFFORDABILITY", res["reason_codes"])
        self.assertGreaterEqual(res["offer"]["dscr"], 1.6)
        r = example_request("approved")
        r["checks"]["fraud"] = "flagged"
        res = evaluate(r, staff_review=False)
        self.assertEqual((res["decision"], res["reason_codes"]), ("DECLINED", ["CHECKS_NOT_PASSED"]))
        r["checks"]["fraud"] = "clear"
        r["checks"]["authority"] = "unverified"
        res = evaluate(r, staff_review=False)
        self.assertEqual((res["decision"], res["next_action"]), ("NEED_INFO", "PROVIDE_INFORMATION"))

    def test_medium_band(self):
        r = example_request("approved")
        r["company"]["age_months"] = 18                        
        r["financials"]["revenue_cv_12m"] = 0.4                
        r["financials"]["largest_customer_share"] = 0.7        
        r["checks"]["max_overdue_days_12m"] = 45               
        res = evaluate(r)
        self.assertEqual((res["risk"]["score"], res["risk"]["band"]), (50, "MEDIUM"))
        self.assertEqual(res["decision"], "MANUAL_REVIEW")
        auto = evaluate(r, staff_review=False)
        self.assertIn(auto["decision"], ("APPROVED", "COUNTEROFFER", "DECLINED"))

    def test_deterministic_and_no_mutation(self):
        req = example_request("counteroffer")
        snap = copy.deepcopy(req)
        self.assertEqual(evaluate(req), evaluate(req))
        self.assertEqual(req, snap)
        self.assertEqual(input_hash(req), input_hash(snap))

    def test_validation(self):
        bad = []
        r = example_request(); r["financials"]["revenue_cv_12m"] = None; bad.append(r)
        r = example_request(); r["extra"] = 1; bad.append(r)
        r = example_request(); r["requested_amount_rub"] = True; bad.append(r)
        r = example_request(); r["financials"]["monthly_revenue_rub"] = float("nan"); bad.append(r)
        r = example_request(); r["financials"]["monthly_revenue_rub"] = 0; bad.append(r)
        r = example_request(); r["product_id"] = "mortgage"; bad.append(r)
        r = example_request(); r["product_id"] = ["working_capital"]; bad.append(r)
        r = example_request(); r["product_id"] = {}; bad.append(r)
        r = example_request(); r["checks"]["fraud"] = "maybe"; bad.append(r)
        r = example_request(); del r["checks"]["registry"]; bad.append(r)
        r = example_request(); r["requested_term_months"] = 0; bad.append(r)
        r = example_request(); r["application_id"] = "x" * 101; bad.append(r)
        r = example_request(); r["financials"]["monthly_revenue_rub"] = 0.5; bad.append(r)
        r = example_request(); r["financials"]["revenue_cv_12m"] = 11; bad.append(r)
        for r in bad:
            with self.assertRaises(RequestError):
                evaluate(r)
        with self.assertRaises(RequestError):
            evaluate([])

    def test_annuity(self):
        self.assertEqual(annuity_payment(1_000_000, D("0.24"), 24), D("52871.10"))
        self.assertEqual(annuity_payment(12_000, D("0.12"), 12), D("1066.19"))

    def test_status_map_and_public_view(self):
        self.assertEqual({d: to_application_status(d) for d in DECISIONS}, STATUS_MAP)
        r = example_request("approved")
        r["checks"]["fraud"] = "flagged"
        pub = public_view(evaluate(r))
        self.assertNotIn("flagged", json.dumps(pub).lower())     # antifraud detail never leaks
        self.assertEqual((pub["status"], pub["reason_codes"]), ("MANUAL_REVIEW", ["CHECKS_REQUIRE_REVIEW"]))
        self.assertTrue(all(x["text"] for x in pub["reasons"]))

    def test_describe_and_json_roundtrip(self):
        json.dumps(describe(), ensure_ascii=False)
        for kind in EXAMPLE_KINDS:
            json.dumps(evaluate(example_request(kind)))

    def test_property_random_requests(self):
        rnd = random.Random(42)
        seen = set()
        for i in range(600):
            req = _base_request()
            req["product_id"] = rnd.choice(list(POLICY["products"]))
            req["requested_amount_rub"] = rnd.randint(50, 6000) * 1000 + rnd.choice([0, 0, 500])
            req["requested_term_months"] = rnd.randint(1, 60)
            req["company"]["age_months"] = rnd.randint(0, 120)
            rev = rnd.randint(100, 3000) * 1000
            req["financials"].update(
                monthly_revenue_rub=rev,
                monthly_cash_available_for_debt_service_rub=int(rev * rnd.uniform(-0.05, 0.6)),
                existing_monthly_debt_service_rub=rnd.randint(0, 300) * 1000,
                revenue_cv_12m=round(rnd.uniform(0, 0.8), 2),
                largest_customer_share=round(rnd.uniform(0, 1), 2),
            )
            req["checks"].update(max_overdue_days_12m=rnd.choice([0, 0, 0, 5, 40, 100]))
            for staff in (True, False):
                res = evaluate(req, staff_review=staff)
                seen.update(res["reason_codes"])
                self.assertIn(res["decision"], DECISIONS)
                self.assertIn(res["next_action"], set(NEXT_ACTION.values()) | {"CHANGE_PRODUCT"})
                if not staff:
                    self.assertNotEqual(res["decision"], "MANUAL_REVIEW")
                o = res["offer"]
                if res["decision"] in ("APPROVED", "COUNTEROFFER"):
                    prod = POLICY["products"][req["product_id"]]
                    f = req["financials"]
                    cash, debt = _dec(f["monthly_cash_available_for_debt_service_rub"]), _dec(f["existing_monthly_debt_service_rub"])
                    need = POLICY["dscr_min_strict"] if "STRICTER_AFFORDABILITY" in res["reason_codes"] else POLICY["dscr_min"]
                    self.assertEqual(o["amount_rub"] % 1000, 0)
                    self.assertTrue(prod["min_amount_rub"] <= o["amount_rub"] <= min(prod["max_amount_rub"], req["requested_amount_rub"]))
                    self.assertTrue(prod["min_term_months"] <= o["term_months"] <= prod["max_term_months"])
                    self.assertGreaterEqual(cash / (debt + _dec(o["monthly_payment_rub"])), need)
                    nxt = o["amount_rub"] + 1000
                    cap = min(prod["max_amount_rub"], req["requested_amount_rub"])
                    if nxt <= cap:   
                        pay = annuity_payment(nxt, D(str(o["annual_rate"])), o["term_months"])
                        self.assertLess(cash / (debt + pay), need)
                    same = o["amount_rub"] == req["requested_amount_rub"] and o["term_months"] == req["requested_term_months"]
                    self.assertEqual(res["decision"], "APPROVED" if same else "COUNTEROFFER")
                else:
                    self.assertIsNone(o)
        self.assertLessEqual(seen, set(REASON_TEXT_RU), seen - set(REASON_TEXT_RU))


def _main(argv=None):
    p = argparse.ArgumentParser(prog="credit_engine", description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evaluate"); e.add_argument("path"); e.add_argument("--no-staff", action="store_true")
    e.add_argument("--public", action="store_true", help="client-safe view")
    sub.add_parser("describe")
    x = sub.add_parser("example"); x.add_argument("kind", choices=EXAMPLE_KINDS)
    sub.add_parser("test")
    a = p.parse_args(argv)

    dump = lambda o: print(json.dumps(o, ensure_ascii=False, indent=2))
    if a.cmd == "evaluate":
        raw = sys.stdin.read() if a.path == "-" else open(a.path, encoding="utf-8").read()
        try:
            res = evaluate(json.loads(raw), staff_review=not a.no_staff)
        except RequestError as err:
            dump({"error": "invalid_request", "details": err.errors})
            return 2
        dump(public_view(res) if a.public else res)
    elif a.cmd == "describe":
        dump(describe())
    elif a.cmd == "example":
        dump(example_request(a.kind))
    else:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(EngineTests)
        ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
