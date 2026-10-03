"""Apollo API client for company search, people search, enrichment, and phone polling."""

from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://api.apollo.io/api/v1"
DEFAULT_WEBHOOK_URL = "https://example.com/contactfinder-phone-webhook"
BULK_ENRICH_SIZE = 10

SENIORITY_LABELS = {
    "owner": "Owner",
    "founder": "Founder",
    "c_suite": "C-suite",
    "partner": "Partner",
    "vp": "VP",
    "head": "Head",
    "director": "Director",
    "manager": "Manager",
    "senior": "Senior",
    "entry": "Entry",
    "intern": "Intern",
}


class ApolloError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def csv_safe(value: str) -> str:
    if value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def location_of(record: dict[str, Any] | None) -> str:
    if not isinstance(record, dict):
        return ""
    parts = [record.get("city"), record.get("state"), record.get("country")]
    joined = ", ".join(str(part) for part in parts if part)
    if joined:
        return joined
    for key in ("raw_address", "organization_raw_address", "formatted_address"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def employee_count(org: dict[str, Any]) -> int | None:
    for key in ("estimated_num_employees", "employee_count", "num_employees"):
        value = org.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def format_phone(entry: dict[str, Any]) -> str:
    number = entry.get("raw_number") or entry.get("sanitized_number") or ""
    if not isinstance(number, str):
        number = str(number or "")
    number = number.strip()
    if not number:
        return ""
    kind = entry.get("type_cd") or ""
    if isinstance(kind, str) and kind and kind not in {"other", "null"}:
        return f"{number} ({kind.replace('_', ' ')})"
    return number


def join_phones(entries: list[Any] | None) -> str:
    numbers: list[str] = []
    seen: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        number = format_phone(entry)
        key = (entry.get("sanitized_number") or number).strip()
        if number and key not in seen:
            seen.add(key)
            numbers.append(number)
    return "; ".join(numbers)


def seniority_label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return SENIORITY_LABELS.get(value.strip(), value.replace("_", " ").title())


def display_name(record: dict[str, Any]) -> str:
    name = record.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    first = str(record.get("first_name") or "").strip()
    last = str(record.get("last_name") or record.get("last_name_obfuscated") or "").strip()
    return f"{first} {last}".strip()


def company_summary(org: dict[str, Any]) -> dict[str, Any]:
    employees = employee_count(org)
    founded = org.get("founded_year")
    return {
        "id": org.get("id") or "",
        "name": org.get("name") or "",
        "domain": org.get("primary_domain") or "",
        "website": org.get("website_url") or "",
        "linkedin_url": org.get("linkedin_url") or "",
        "phone": org.get("phone") or "",
        "employees": employees,
        "founded_year": founded if isinstance(founded, int) and founded > 0 else None,
        "location": location_of(org),
    }


def contact_from_search(person: dict[str, Any], company: dict[str, Any]) -> dict[str, str]:
    organization = person.get("organization") if isinstance(person.get("organization"), dict) else {}
    return {
        "id": str(person.get("id") or ""),
        "name": display_name(person),
        "designation": str(person.get("title") or ""),
        "email": "",
        "phone": "",
        "linkedin_url": "",
        "company": str(organization.get("name") or company.get("name") or ""),
        "domain": str(company.get("domain") or ""),
        "location": "",
        "seniority": "",
    }


def contact_from_match(match: dict[str, Any], company: dict[str, Any]) -> dict[str, str]:
    organization = match.get("organization") if isinstance(match.get("organization"), dict) else {}
    return {
        "id": str(match.get("id") or ""),
        "name": display_name(match),
        "designation": str(match.get("title") or ""),
        "email": str(match.get("email") or ""),
        "phone": join_phones(match.get("phone_numbers")),
        "linkedin_url": str(match.get("linkedin_url") or ""),
        "company": str(organization.get("name") or company.get("name") or ""),
        "domain": str(organization.get("primary_domain") or company.get("domain") or ""),
        "location": location_of(match),
        "seniority": seniority_label(match.get("seniority")),
    }


def phones_by_person(payload: dict[str, Any]) -> dict[str, str]:
    result = payload.get("webhook_result")
    if not isinstance(result, dict):
        result = payload
    people = result.get("people") if isinstance(result, dict) else None
    found: dict[str, str] = {}
    if not isinstance(people, list):
        return found
    for person in people:
        if not isinstance(person, dict) or not person.get("id"):
            continue
        phones = join_phones(person.get("phone_numbers"))
        if phones:
            found[str(person["id"])] = phones
    return found


def error_message(response: httpx.Response) -> str:
    text = (response.text or "").strip()
    try:
        data = response.json()
    except ValueError:
        return text[:500] or f"Apollo returned HTTP {response.status_code}."
    if isinstance(data, dict):
        for key in ("error_message", "message", "error"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        code = data.get("error_code")
        if code:
            return str(code).replace("_", " ")
    if isinstance(data, str) and data.strip():
        return data.strip()[:500]
    return text[:500] or f"Apollo returned HTTP {response.status_code}."


class ApolloClient:
    def __init__(self, api_key: str, webhook_url: str = DEFAULT_WEBHOOK_URL):
        self.api_key = api_key
        self.webhook_url = webhook_url or DEFAULT_WEBHOOK_URL

    async def search_companies(self, name: str) -> list[dict[str, Any]]:
        data = await self._request(
            "POST",
            "/mixed_companies/search",
            params=[
                ("q_organization_name", name),
                ("page", "1"),
                ("per_page", "8"),
            ],
        )
        organizations = data.get("organizations") if isinstance(data, dict) else None
        if not isinstance(organizations, list):
            return []
        companies = []
        for org in organizations:
            if isinstance(org, dict) and org.get("id") and org.get("name"):
                companies.append(company_summary(org))
        return companies

    async def search_people(
        self,
        organization_id: str,
        titles: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        params: list[tuple[str, str]] = [
            ("organization_ids[]", organization_id),
            ("include_similar_titles", "true"),
            ("page", "1"),
            ("per_page", str(limit)),
        ]
        params.extend(("person_titles[]", title) for title in titles)
        data = await self._request("POST", "/mixed_people/api_search", params=params)
        people = data.get("people") if isinstance(data, dict) else None
        if not isinstance(people, list):
            return []
        return [person for person in people if isinstance(person, dict) and person.get("id")]

    async def enrich_batch(self, person_ids: list[str], reveal_phone: bool) -> dict[str, Any]:
        params = [
            ("reveal_personal_emails", "false"),
            ("reveal_phone_number", "true" if reveal_phone else "false"),
        ]
        if reveal_phone:
            params.append(("webhook_url", self.webhook_url))
        data = await self._request(
            "POST",
            "/people/bulk_match",
            params=params,
            json={"details": [{"id": person_id} for person_id in person_ids]},
        )
        return data if isinstance(data, dict) else {}

    async def poll_phones(self, request_id: str) -> dict[str, Any]:
        response = await self._raw("GET", f"/webhook_result/{request_id}")
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ApolloError(502, "Apollo returned an unreadable phone result.") from exc
            if not isinstance(payload, dict):
                raise ApolloError(502, "Apollo returned an unreadable phone result.")
            status = str(payload.get("webhook_status") or "").lower()
            if status in {"failed", "failure", "error"}:
                reason = payload.get("failure_reason") or "Phone lookup failed."
                return {"status": "failed", "message": str(reason), "phones": {}}
            return {
                "status": "ready",
                "message": "",
                "phones": phones_by_person(payload),
                "retry_after_seconds": None,
            }

        try:
            payload = response.json()
        except ValueError:
            payload = {}
        code = payload.get("error_code") if isinstance(payload, dict) else None
        if response.status_code == 404 and code == "result_pending":
            retry = payload.get("retry_after_seconds") if isinstance(payload, dict) else None
            return {
                "status": "pending",
                "message": "Phone numbers are still being looked up.",
                "phones": {},
                "retry_after_seconds": retry if isinstance(retry, int) else 8,
            }
        if code in {"request_id_unknown", "request_id_expired", "invalid_request_id"}:
            return {
                "status": "failed",
                "message": str(code).replace("_", " "),
                "phones": {},
                "retry_after_seconds": None,
            }
        raise ApolloError(response.status_code, error_message(response))

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._raw(method, path, **kwargs)
        if response.status_code >= 400:
            status = response.status_code if 400 <= response.status_code < 600 else 502
            raise ApolloError(status, error_message(response))
        try:
            data = response.json()
        except ValueError as exc:
            raise ApolloError(502, "Apollo returned a response that was not JSON.") from exc
        return data if isinstance(data, dict) else {}

    async def _raw(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                return await client.request(method, f"{BASE_URL}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ApolloError(502, "Could not reach Apollo. Check your connection and try again.") from exc
