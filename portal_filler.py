from __future__ import annotations

import logging
import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from database import Job
from doc_generator import GeneratedDocs
from resume_parser import ResumeData

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[str, str, int], None] | None

PORTAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "indeed": re.compile(r"(?:^|//)(?:www\.)?indeed\.com/(?:viewjob|jobs)|(?:^|//)apply\.indeed\.com", re.IGNORECASE),
    "greenhouse": re.compile(r"boards\.greenhouse\.io|app\.greenhouse\.io", re.IGNORECASE),
    "lever": re.compile(r"jobs\.lever\.co", re.IGNORECASE),
    "workday": re.compile(r"myworkdayjobs\.com|wd\d+\.myworkdayjobs\.com", re.IGNORECASE),
    "icims": re.compile(r"\.icims\.com", re.IGNORECASE),
    "taleo": re.compile(r"taleo\.net", re.IGNORECASE),
    "smartrecruiters": re.compile(r"smartrecruiters\.com", re.IGNORECASE),
}


def detect_platform(url: str) -> str:
    for platform, pattern in PORTAL_PATTERNS.items():
        if pattern.search(url or ""):
            return platform
    return "unknown"


@dataclass(slots=True)
class PortalResult:
    status: str
    message: str
    platform: str = "unknown"
    screenshot_path: Path | None = None


@dataclass(slots=True)
class PortalAutofillReadiness:
    ready: bool
    summary: str
    reason_code: str
    technical_detail: str = ""


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _format_technical_detail(exc: BaseException) -> str:
    parts: list[str] = []
    for item in _exception_chain(exc):
        text = str(item).strip()
        if text:
            parts.append(f"{type(item).__name__}: {text}")
        else:
            parts.append(type(item).__name__)
    return " | ".join(parts)


def _classify_launch_failure(exc: BaseException) -> tuple[str, str, str]:
    detail = _format_technical_detail(exc)
    lowered = detail.lower()
    if "winerror 5" in lowered or "access is denied" in lowered:
        return (
            "browser_launch_failed",
            "Portal autofill: unavailable (Chromium launch failed)",
            "winerror_5_access_denied",
        )
    if "create_subprocess" in lowered or "subprocess" in lowered or "notimplementederror" in lowered:
        return (
            "browser_launch_failed",
            "Portal autofill: unavailable (Chromium launch failed)",
            "subprocess_creation_failed",
        )
    if "executable" in lowered or "browser" in lowered or "install" in lowered:
        return (
            "missing_browser_runtime",
            "Portal autofill: unavailable (Chromium runtime missing)",
            "browser_executable_launch_failed",
        )
    return (
        "browser_launch_failed",
        "Portal autofill: unavailable (Chromium launch failed)",
        type(exc).__name__,
    )


def _emit(cb: ProgressCallback, stage: str, message: str, progress: int) -> None:
    if cb:
        cb(stage, message, progress)


def _extract_linkedin(header_lines: list[str]) -> str:
    for line in header_lines:
        if "linkedin.com" not in line.lower():
            continue
        match = re.search(r"https?://[^\s]+linkedin\.com/[^\s]+", line, re.IGNORECASE)
        if match:
            return match.group(0)
        stripped = line.strip()
        if "linkedin.com/in/" in stripped.lower():
            return stripped if stripped.startswith("http") else f"https://{stripped}"
    return ""


def _extract_website(header_lines: list[str]) -> str:
    for line in header_lines:
        if not any(token in line.lower() for token in ("github.com", "portfolio", "website")):
            continue
        match = re.search(r"https?://[^\s]+", line)
        if match:
            return match.group(0)
    return ""


def _name_parts(resume: ResumeData) -> tuple[str, str]:
    name = (resume.name or "").strip()
    parts = name.split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (name, "")


def _current_company(resume: ResumeData) -> str:
    if not resume.work_experience_entries:
        return ""
    role_line = resume.work_experience_entries[0].role_line or ""
    for sep in (" | ", " at ", " - ", " — "):
        if sep in role_line:
            return role_line.split(sep, 1)[-1].strip()
    return ""


def _best_resume_file(docs: GeneratedDocs) -> str | None:
    if docs.resume_pdf_path and docs.resume_pdf_path != Path() and docs.resume_pdf_path.exists():
        return str(docs.resume_pdf_path)
    if docs.resume_docx_path and docs.resume_docx_path != Path() and docs.resume_docx_path.exists():
        return str(docs.resume_docx_path)
    return None


def _best_cover_letter_file(docs: GeneratedDocs) -> str | None:
    if docs.cover_letter_pdf_path and docs.cover_letter_pdf_path != Path() and docs.cover_letter_pdf_path.exists():
        return str(docs.cover_letter_pdf_path)
    if docs.cover_letter_docx_path and docs.cover_letter_docx_path != Path() and docs.cover_letter_docx_path.exists():
        return str(docs.cover_letter_docx_path)
    if docs.cover_letter_txt_path and docs.cover_letter_txt_path != Path() and docs.cover_letter_txt_path.exists():
        return str(docs.cover_letter_txt_path)
    return None


def _output_dir(docs: GeneratedDocs) -> Path | None:
    if docs.output_dir and docs.output_dir != Path():
        return docs.output_dir
    return None


class _BaseHandler:
    PAGE_TIMEOUT = 30_000
    FIELD_TIMEOUT = 5_000
    CONFIRM_TIMEOUT = 15_000

    CAPTCHA_SELECTORS = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        ".g-recaptcha",
        ".h-captcha",
        "[data-sitekey]",
        "#captcha",
    ]
    LOGIN_PHRASES = [
        "sign in to apply",
        "log in to apply",
        "create an account to apply",
        "sign in required",
        "please sign in",
    ]
    SUCCESS_PHRASES = [
        "application submitted",
        "thank you for applying",
        "application received",
        "successfully submitted",
        "we've received your application",
        "thanks for applying",
        "you've applied",
    ]
    SCREENING_PHRASES = [
        "screening questions",
        "additional questions",
        "assessment",
        "work authorization",
        "years of experience",
    ]

    def __init__(self, page, resume: ResumeData, docs: GeneratedDocs, job: Job, cb: ProgressCallback) -> None:
        self.page = page
        self.resume = resume
        self.docs = docs
        self.job = job
        self.cb = cb

    def _has_captcha(self) -> bool:
        for selector in self.CAPTCHA_SELECTORS:
            try:
                if self.page.query_selector(selector):
                    return True
            except Exception:
                continue
        return False

    def _has_login_wall(self) -> bool:
        try:
            content = self.page.content().lower()
        except Exception:
            return False
        if any(phrase in content for phrase in self.LOGIN_PHRASES):
            return True
        try:
            has_password = bool(self.page.query_selector("input[type='password']"))
            has_name = bool(self.page.query_selector("input[name*='first'], input[id*='first'], input[placeholder*='First']"))
            return has_password and not has_name
        except Exception:
            return False

    def _confirm_success(self) -> bool:
        try:
            self.page.wait_for_load_state("networkidle", timeout=self.CONFIRM_TIMEOUT)
        except Exception:
            pass
        try:
            content = self.page.content().lower()
            return any(phrase in content for phrase in self.SUCCESS_PHRASES)
        except Exception:
            return False

    def _page_content_lower(self) -> str:
        try:
            return self.page.content().lower()
        except Exception:
            return ""

    def _fill_field(self, selector: str, value: str) -> bool:
        try:
            element = self.page.wait_for_selector(selector, timeout=self.FIELD_TIMEOUT)
            if element:
                element.fill(value)
                return True
        except Exception:
            return False
        return False

    def _try_fill(self, selectors: list[str], value: str) -> bool:
        if not value:
            return False
        for selector in selectors:
            if self._fill_field(selector, value):
                return True
        return False

    def _upload_file(self, selectors: list[str], path: str) -> bool:
        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element:
                    element.set_input_files(path)
                    return True
            except Exception:
                continue
        return False

    def _click_submit(self, selectors: list[str]) -> bool:
        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    element.click()
                    return True
            except Exception:
                continue
        return False

    def _screenshot(self, label: str) -> Path | None:
        output_dir = _output_dir(self.docs)
        if not output_dir:
            return None

    def _has_screening_questions(self) -> bool:
        content = self._page_content_lower()
        if any(phrase in content for phrase in self.SCREENING_PHRASES):
            return True
        selectors = [
            "select",
            "textarea",
            "input[type='radio']",
            "input[type='checkbox']",
            "[data-testid*='question']",
            "[class*='question']",
        ]
        found_complex_question = False
        for selector in selectors:
            try:
                if self.page.query_selector(selector):
                    found_complex_question = True
                    break
            except Exception:
                continue
        return found_complex_question and ("resume" not in content or "cover letter" not in content)
        try:
            path = output_dir / f"portal_{label}.png"
            self.page.screenshot(path=str(path))
            return path
        except Exception:
            return None

    def fill(self) -> PortalResult:
        raise NotImplementedError


class GreenhouseHandler(_BaseHandler):
    def fill(self) -> PortalResult:
        _emit(self.cb, "portal_fill", "Loading Greenhouse application form...", 2)
        try:
            self.page.wait_for_load_state("networkidle", timeout=self.PAGE_TIMEOUT)
        except Exception:
            pass
        if self._has_captcha():
            return PortalResult("captcha", "CAPTCHA detected on Greenhouse form.", "greenhouse")
        if self._has_login_wall():
            return PortalResult("login_required", "Login wall detected on Greenhouse form.", "greenhouse")

        _emit(self.cb, "portal_fill", "Filling Greenhouse contact fields...", 3)
        first, last = _name_parts(self.resume)
        self._try_fill(["input#first_name", "input[name='job_application[first_name]']", "input[placeholder*='First']"], first)
        self._try_fill(["input#last_name", "input[name='job_application[last_name]']", "input[placeholder*='Last']"], last)
        self._try_fill(["input#email", "input[name='job_application[email]']", "input[type='email']"], self.resume.email or "")
        self._try_fill(["input#phone", "input[name='job_application[phone]']", "input[type='tel']"], self.resume.phone or "")

        _emit(self.cb, "portal_fill", "Uploading resume and cover letter...", 4)
        resume_file = _best_resume_file(self.docs)
        if resume_file:
            self._upload_file(
                ["input#resume", "input[name='job_application[resume]']", "input[type='file'][id*='resume']", "input[type='file']"],
                resume_file,
            )
        cover_letter_file = _best_cover_letter_file(self.docs)
        if cover_letter_file:
            self._upload_file(
                ["input#cover_letter", "input[name='job_application[cover_letter]']", "input[type='file'][id*='cover']"],
                cover_letter_file,
            )

        self._try_fill(["input#job_application_linkedin_url", "input[name*='linkedin']", "input[placeholder*='LinkedIn']"], _extract_linkedin(self.resume.header_lines or []))
        self._try_fill(["input#job_application_website", "input[name*='website']", "input[placeholder*='Portfolio']"], _extract_website(self.resume.header_lines or []))

        if self._has_captcha():
            return PortalResult("captcha", "CAPTCHA appeared before submit on Greenhouse form.", "greenhouse")

        _emit(self.cb, "portal_fill", "Submitting Greenhouse application...", 5)
        submitted = self._click_submit([
            "input[type='submit']",
            "button[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
        ])
        if not submitted:
            return PortalResult("error", "Could not find or click submit button on Greenhouse form.", "greenhouse", self._screenshot("greenhouse_submit_fail"))

        _emit(self.cb, "portal_fill", "Confirming Greenhouse submission...", 6)
        if not self._confirm_success():
            return PortalResult("error", "Greenhouse submit clicked but confirmation not detected.", "greenhouse", self._screenshot("greenhouse_confirm_fail"))
        return PortalResult("submitted", f"Submitted via Greenhouse for {self.job.title} at {self.job.employer}.", "greenhouse")


class LeverHandler(_BaseHandler):
    def fill(self) -> PortalResult:
        _emit(self.cb, "portal_fill", "Loading Lever application form...", 2)
        try:
            self.page.wait_for_load_state("networkidle", timeout=self.PAGE_TIMEOUT)
        except Exception:
            pass
        if self._has_captcha():
            return PortalResult("captcha", "CAPTCHA detected on Lever form.", "lever")
        if self._has_login_wall():
            return PortalResult("login_required", "Login wall detected on Lever form.", "lever")

        _emit(self.cb, "portal_fill", "Filling Lever contact fields...", 3)
        self._try_fill(["input[name='name']", "input#name", "input[placeholder*='Full name']", "input[placeholder*='Name']"], self.resume.name or "")
        self._try_fill(["input[name='email']", "input#email", "input[type='email']"], self.resume.email or "")
        self._try_fill(["input[name='phone']", "input#phone", "input[type='tel']"], self.resume.phone or "")

        _emit(self.cb, "portal_fill", "Uploading resume...", 4)
        resume_file = _best_resume_file(self.docs)
        if resume_file:
            self._upload_file(
                ["input[type='file'][name='resume']", "input[type='file'][id*='resume']", "input[type='file']"],
                resume_file,
            )

        self._try_fill(["input[name='org']", "input[placeholder*='current company']", "input[placeholder*='Company']"], _current_company(self.resume))
        self._try_fill(["input[name='urls[LinkedIn]']", "input[placeholder*='LinkedIn']", "input[name*='linkedin']"], _extract_linkedin(self.resume.header_lines or []))

        if self._has_captcha():
            return PortalResult("captcha", "CAPTCHA appeared before submit on Lever form.", "lever")

        _emit(self.cb, "portal_fill", "Submitting Lever application...", 5)
        submitted = self._click_submit([
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit application')",
            "button:has-text('Apply')",
            "button:has-text('Submit')",
        ])
        if not submitted:
            return PortalResult("error", "Could not find or click submit button on Lever form.", "lever", self._screenshot("lever_submit_fail"))

        _emit(self.cb, "portal_fill", "Confirming Lever submission...", 6)
        if not self._confirm_success():
            return PortalResult("error", "Lever submit clicked but confirmation not detected.", "lever", self._screenshot("lever_confirm_fail"))
        return PortalResult("submitted", f"Submitted via Lever for {self.job.title} at {self.job.employer}.", "lever")


class GenericHandler(_BaseHandler):
    def fill(self) -> PortalResult:
        _emit(self.cb, "portal_fill", "Loading application form...", 2)
        try:
            self.page.wait_for_load_state("networkidle", timeout=self.PAGE_TIMEOUT)
        except Exception:
            pass
        if self._has_captcha():
            return PortalResult("captcha", "CAPTCHA detected on the application page.", "unknown")
        if self._has_login_wall():
            return PortalResult("login_required", "Login wall detected on the application page.", "unknown")
        return PortalResult("unsupported", f"Portal not supported for autofill: {self.job.apply_url}", "unknown")


class IndeedHandler(_BaseHandler):
    HOSTED_FORM_SELECTORS = [
        "input[type='file']",
        "input[name*='resume']",
        "input[placeholder*='Full name']",
        "input[placeholder*='Phone']",
        "input[type='email']",
        "button[type='submit']",
        "[data-testid*='apply']",
    ]

    def _current_url(self) -> str:
        return str(getattr(self.page, "url", "") or self.job.apply_url or "")

    def _is_indeed_domain(self) -> bool:
        return "indeed.com" in self._current_url().lower()

    def _looks_like_posting_page(self) -> bool:
        url = self._current_url().lower()
        if "/viewjob" in url and "apply.indeed.com" not in url:
            return True
        content = self._page_content_lower()
        return "job details" in content and "apply now" not in content and "continue to application" not in content

    def _looks_like_hosted_form(self) -> bool:
        url = self._current_url().lower()
        if "apply.indeed.com" in url:
            return True
        content = self._page_content_lower()
        if "indeed apply" in content or "apply with your indeed resume" in content:
            return True
        for selector in self.HOSTED_FORM_SELECTORS:
            try:
                if self.page.query_selector(selector):
                    return True
            except Exception:
                continue
        return False

    def fill(self) -> PortalResult:
        _emit(self.cb, "portal_fill", "Loading Indeed application form...", 2)
        try:
            self.page.wait_for_load_state("networkidle", timeout=self.PAGE_TIMEOUT)
        except Exception:
            pass
        if self._has_captcha():
            return PortalResult("captcha", "CAPTCHA detected on Indeed.", "indeed")
        if self._has_login_wall():
            return PortalResult("login_required", "Login wall detected on Indeed.", "indeed")
        if not self._is_indeed_domain():
            return PortalResult("unsupported", "Indeed redirected to an external employer application page.", "indeed")
        if self._looks_like_posting_page():
            return PortalResult("unsupported", "Indeed posting page is not an automatable Indeed apply form.", "indeed")
        if not self._looks_like_hosted_form():
            return PortalResult("unsupported", "Indeed page shape is not recognized as a hosted apply form.", "indeed")
        if self._has_screening_questions():
            return PortalResult("screening_questions", "Indeed apply flow includes screening questions that require manual review.", "indeed")

        _emit(self.cb, "portal_fill", "Filling Indeed contact fields...", 3)
        self._try_fill(
            ["input[name*='name']", "input[id*='name']", "input[placeholder*='Full name']", "input[autocomplete='name']"],
            self.resume.name or "",
        )
        self._try_fill(
            ["input[name*='email']", "input[id*='email']", "input[type='email']", "input[autocomplete='email']"],
            self.resume.email or "",
        )
        self._try_fill(
            ["input[name*='phone']", "input[id*='phone']", "input[type='tel']", "input[autocomplete='tel']"],
            self.resume.phone or "",
        )

        _emit(self.cb, "portal_fill", "Uploading resume...", 4)
        resume_file = _best_resume_file(self.docs)
        if resume_file:
            self._upload_file(
                ["input[type='file'][name*='resume']", "input[type='file'][id*='resume']", "input[type='file']"],
                resume_file,
            )
        cover_letter_file = _best_cover_letter_file(self.docs)
        if cover_letter_file:
            self._upload_file(
                ["input[type='file'][name*='cover']", "input[type='file'][id*='cover']"],
                cover_letter_file,
            )
        if self._has_screening_questions():
            return PortalResult("screening_questions", "Indeed apply flow surfaced screening questions after basic fields.", "indeed")
        if self._has_captcha():
            return PortalResult("captcha", "CAPTCHA appeared before submit on Indeed.", "indeed")

        _emit(self.cb, "portal_fill", "Submitting Indeed application...", 5)
        submitted = self._click_submit(
            [
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Submit application')",
                "button:has-text('Apply now')",
                "button:has-text('Continue')",
            ]
        )
        if not submitted:
            return PortalResult("unsupported", "Indeed apply form did not expose a safe final submit action.", "indeed", self._screenshot("indeed_submit_missing"))

        _emit(self.cb, "portal_fill", "Confirming Indeed submission...", 6)
        if not self._confirm_success():
            return PortalResult("unsupported", "Indeed submit clicked but confirmation was not detected safely.", "indeed", self._screenshot("indeed_confirm_fail"))
        return PortalResult("submitted", f"Submitted via Indeed for {self.job.title} at {self.job.employer}.", "indeed")


_HANDLER_MAP: dict[str, type[_BaseHandler]] = {
    "indeed": IndeedHandler,
    "greenhouse": GreenhouseHandler,
    "lever": LeverHandler,
}


class PortalFiller:
    def __init__(self, *, headless: bool = True) -> None:
        self.headless = headless

    @staticmethod
    def check_readiness() -> PortalAutofillReadiness:
        try:
            playwright_module = importlib.import_module("playwright.sync_api")
        except ImportError as exc:
            return PortalAutofillReadiness(
                ready=False,
                summary="Portal autofill: unavailable (Playwright not installed)",
                reason_code="missing_playwright",
                technical_detail=_format_technical_detail(exc),
            )
        sync_playwright_fn = getattr(playwright_module, "sync_playwright", None)
        if sync_playwright_fn is None:
            return PortalAutofillReadiness(
                ready=False,
                summary="Portal autofill: unavailable (Playwright import incomplete)",
                reason_code="missing_playwright",
                technical_detail="sync_playwright missing from playwright.sync_api",
            )
        try:
            with sync_playwright_fn() as playwright:
                browser = playwright.chromium.launch(headless=True)
                browser.close()
        except Exception as exc:
            reason_code, summary, detail_code = _classify_launch_failure(exc)
            return PortalAutofillReadiness(
                ready=False,
                summary=summary,
                reason_code=reason_code,
                technical_detail=f"{detail_code}: {_format_technical_detail(exc)}",
            )
        return PortalAutofillReadiness(
            ready=True,
            summary="Portal autofill: ready",
            reason_code="ready",
            technical_detail="Chromium headless launch succeeded.",
        )

    def fill(
        self,
        job: Job,
        resume: ResumeData,
        docs: GeneratedDocs,
        *,
        progress_callback: ProgressCallback = None,
    ) -> PortalResult:
        readiness = self.check_readiness()
        if not readiness.ready:
            return PortalResult("unavailable", readiness.summary, "unknown")
        platform = detect_platform(job.apply_url or "")
        _emit(progress_callback, "portal_detect", f"Detected portal: {platform}", 1)
        LOGGER.info("PortalFiller: job=%s platform=%s url=%s", job.id, platform, job.apply_url)

        if sync_playwright is None:
            return PortalResult("unsupported", "Playwright is not installed for portal autofill.", platform)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()
                _emit(progress_callback, "portal_navigate", "Opening application page...", 2)
                page.goto(job.apply_url or "", timeout=30_000, wait_until="domcontentloaded")
                handler_cls = _HANDLER_MAP.get(platform, GenericHandler)
                result = handler_cls(page, resume, docs, job, progress_callback).fill()
                browser.close()
                return result
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unexpected PortalFiller error for job %s", job.id)
            return PortalResult("error", f"Unexpected portal error: {exc}", platform)
