from __future__ import annotations

import copy
import logging
import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from application_routing import EmailApplyAssessment, assess_email_apply
from config import AppPaths, JobBotConfig, load_or_create_config, save_config
from database import Database
from match_scorer import MatchScorer
from pipeline import JobBotPipeline
from portal_filler import PortalAutofillReadiness
from resume_parser import parse_resume


MODEL_OPTIONS = {
    "ollama_local": ("qwen2.5:7b",),
    "openai": ("gpt-5-mini", "gpt-5-nano"),
    "anthropic": ("claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"),
}

FIELD_TOOLTIPS = {
    "Resume source": "Path to your source resume file. DOCX is recommended for the highest-quality tailoring; PDF and plain text still work.",
    "Source provider": "Choose where jobs are discovered. Adzuna and USAJobs use official APIs; JobSpy scrapes boards by keyword.",
    "JobSpy sites": "Comma-separated JobSpy sites to query. Recommended: indeed, google.",
    "Adzuna app id": "App ID from your Adzuna developer account.",
    "Adzuna app key": "App key from your Adzuna developer account.",
    "Adzuna country": "Adzuna country code, e.g., us, gb, ca.",
    "Results per page": "How many jobs to request per run. Semi-auto defaults to 100; auto defaults to 25.",
    "Cheap stage provider": "Model provider for the low-cost screening pass.",
    "Cheap stage model": "Specific low-cost model used for the cheap screening stage.",
    "Strong stage provider": "Provider used for the higher-confidence scoring stage.",
    "Strong stage model": "Specific model used for the stronger scoring stage.",
    "Doc stage provider": "Provider used for document tailoring notes.",
    "Doc stage model": "Specific model used for document note generation.",
    "Ollama base URL": "Local Ollama server URL used when the cheap stage runs on your machine.",
    "Anthropic API key": "API key for Anthropic-hosted models.",
    "OpenAI API key": "API key for OpenAI-hosted models.",
    "Job keyword": "Primary search phrase sent to the job source.",
    "Location": "Optional job search location. Leave blank for broader searches.",
    "USAJobs account email": "Email address registered with the USAJobs API. Sent as the User-Agent header.",
    "USAJobs authorization key": "API key for USAJobs. Required to avoid 401 Unauthorized responses.",
    "Include titles": "Comma-separated titles that should be treated as good fits.",
    "Exclude titles": "Comma-separated titles the app should skip.",
    "Force escalate keywords": "Comma-separated keywords that always push a job to the stronger review stage.",
    "Salary floor": "Minimum annual salary filter. Use 0 to disable.",
    "Review threshold": "Score at or above this value is worth manual review.",
    "Final apply threshold": "Score at or above this value becomes an apply candidate.",
    "Cheap reject threshold": "Cheap-stage score at or below this value gets rejected early.",
    "Cheap escalate threshold": "Cheap-stage score at or above this value moves to the strong stage.",
    "Pre-cheap reject threshold": "TF-IDF/keyword gate score below this value is rejected before any AI calls.",
    "Fast rank min score": "Minimum local fast-rank score required before a job can enter the progressive shortlist or provisional queue.",
    "Cheap AI top N": "Only the top N fast-ranked jobs are sent to the cheap AI reranker.",
    "Strong AI top N": "Only the top N cheap-stage survivors are sent to the strong AI verifier.",
    "Automation mode": "Semi-auto queues jobs for approval. Auto sends only when the apply method supports it.",
    "Skip AI scoring in semi_auto": "When enabled, semi-auto skips AI scoring and queues deterministic matches right away for faster review.",
    "Enable progressive queue": "Queue provisional fast-ranked jobs immediately, then improve their scores as AI verification finishes.",
    "Enable pre-cheap gate": "Use a fast TF-IDF + keyword overlap check to skip obvious mismatches before AI scoring.",
    "Gmail recipient (optional fallback/test inbox)": "Optional fallback inbox for non-employer delivery or dry-run testing.",
    "Gmail sender": "Authenticated Gmail account used to send applications.",
    "Client secrets path": "Path to your Google OAuth client secrets JSON file.",
    "Enable Gmail delivery": "Turn on Gmail delivery for approved jobs.",
    "Fit to Resume": "Analyze the configured resume with the cheap AI stage and replace Job keyword with suggested search terms you can edit.",
}


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event: object | None = None) -> None:
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            background="#fff8d5",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            wraplength=340,
        )
        label.pack()

    def _hide(self, _event: object | None = None) -> None:
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class JobBotDashboard:
    PORTAL_TEST_ACTION_ID = "__portal_runtime__"

    def __init__(self, root: tk.Tk, config: JobBotConfig, paths: AppPaths, database: Database) -> None:
        self.root = root
        self.config = config
        self.paths = paths
        self.database = database
        self.pipeline = JobBotPipeline(config, paths, database)
        self.status_var = tk.StringVar(value="Ready")
        self.portal_readiness_var = tk.StringVar(value="Portal autofill: checking...")
        self.gmail_readiness_var = tk.StringVar(value="Gmail send readiness: checking...")

        self.resume_var = tk.StringVar(value=config.resume_source_path)
        self.threshold_var = tk.StringVar(value=str(config.scoring_threshold))
        self.final_apply_threshold_var = tk.StringVar(value=str(config.final_apply_threshold))
        self.cheap_reject_threshold_var = tk.StringVar(value=str(config.cheap_reject_threshold))
        self.cheap_escalate_threshold_var = tk.StringVar(value=str(config.cheap_escalate_threshold))
        self.precheap_gate_threshold_var = tk.StringVar(value=str(config.precheap_gate_reject_threshold))
        self.fast_rank_min_score_var = tk.StringVar(value=str(config.fast_rank_min_score))
        self.cheap_ai_top_n_var = tk.StringVar(value=str(config.cheap_ai_top_n))
        self.strong_ai_top_n_var = tk.StringVar(value=str(config.strong_ai_top_n))
        self.keyword_var = tk.StringVar(value=config.source.keyword)
        self.location_var = tk.StringVar(value=config.source.location)
        self.source_provider_var = tk.StringVar(value=config.source.provider)
        self.jobspy_sites_var = tk.StringVar(value=", ".join(config.source.jobspy_sites))
        self.results_per_page_var = tk.StringVar(value=str(config.source.results_per_page))
        self.usajobs_email_var = tk.StringVar(value=config.source.user_agent)
        self.usajobs_auth_key_var = tk.StringVar(value=config.source.authorization_key)
        self.adzuna_app_id_var = tk.StringVar(value=config.source.adzuna_app_id)
        self.adzuna_app_key_var = tk.StringVar(value=config.source.adzuna_app_key)
        self.adzuna_country_var = tk.StringVar(value=config.source.adzuna_country or "us")
        self.include_titles_var = tk.StringVar(value=", ".join(config.include_titles))
        self.exclude_titles_var = tk.StringVar(value=", ".join(config.exclude_titles))
        self.force_keywords_var = tk.StringVar(value=", ".join(config.force_escalate_keywords))
        self.salary_floor_var = tk.StringVar(value=str(config.salary_floor))
        self.gmail_enabled_var = tk.BooleanVar(value=config.gmail.enabled)
        self.skip_ai_scoring_var = tk.BooleanVar(value=config.skip_ai_scoring_in_semi_auto)
        self.progressive_queue_enabled_var = tk.BooleanVar(value=config.progressive_queue_enabled)
        self.precheap_gate_enabled_var = tk.BooleanVar(value=config.precheap_gate_enabled)
        self.automation_mode_var = tk.StringVar(value=config.automation_mode)
        self.llm_provider_var = tk.StringVar(value=config.llm_provider)
        self.cheap_stage_provider_var = tk.StringVar(value=config.cheap_stage_provider)
        self.cheap_stage_model_var = tk.StringVar(value=config.cheap_stage_model)
        self.strong_stage_provider_var = tk.StringVar(value=config.strong_stage_provider)
        self.strong_stage_model_var = tk.StringVar(value=config.strong_stage_model)
        self.doc_stage_provider_var = tk.StringVar(value=config.doc_stage_provider)
        self.doc_stage_model_var = tk.StringVar(value=config.doc_stage_model)
        self.ollama_base_url_var = tk.StringVar(value=config.ollama_base_url)
        self.recipient_var = tk.StringVar(value=config.gmail.recipient_email)
        self.sender_var = tk.StringVar(value=config.gmail.sender_email)
        self.client_secret_var = tk.StringVar(value=config.gmail.client_secrets_file)
        self.anthropic_api_key_var = tk.StringVar(value=config.anthropic_api_key)
        self.openai_api_key_var = tk.StringVar(value=config.openai_api_key)

        self.outcome_var = tk.StringVar(value="no_response")
        self.review_tree: ttk.Treeview | None = None
        self.log_text: tk.Text | None = None
        self.cost_text: tk.Text | None = None
        self.last_run_label: ttk.Label | None = None
        self.details_text: tk.Text | None = None
        self.cheap_stage_model_combo: ttk.Combobox | None = None
        self.strong_stage_model_combo: ttk.Combobox | None = None
        self.doc_stage_model_combo: ttk.Combobox | None = None
        self.setup_canvas: tk.Canvas | None = None
        self._tooltips: list[Tooltip] = []
        self._run_poll_after_id: str | None = None
        self._run_in_progress = False
        self.fit_resume_button: ttk.Button | None = None
        self.generate_button: ttk.Button | None = None
        self.approve_button: ttk.Button | None = None
        self.portal_test_buttons: list[ttk.Button] = []
        self.generate_progress_var = tk.DoubleVar(value=0.0)
        self.generate_status_var = tk.StringVar(value="Idle")
        self.generate_context_var = tk.StringVar(value="No review queue action in progress.")
        self.generate_progressbar: ttk.Progressbar | None = None
        self._review_action_in_progress = False
        self._generate_in_progress = False
        self._review_action_job_id: str | None = None
        self._review_action_mode: str | None = None
        self._review_action_event_queue: queue.Queue[tuple[str, str, int, str | None, str | None]] = queue.Queue()
        self._review_action_poll_after_id: str | None = None
        self._review_rows: list[dict[str, object]] = []
        self._review_sort_column = "score"
        self._review_sort_desc = True
        self._source_provider_user_set = False
        self._build_ui()
        self._refresh_portal_readiness()
        self._refresh_gmail_readiness()
        self.refresh_view()

    def _build_ui(self) -> None:
        self.root.title("Job Bot Demo")
        self.root.geometry("1100x720")
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)

        setup_frame = ttk.Frame(notebook, padding=12)
        run_frame = ttk.Frame(notebook, padding=12)
        review_frame = ttk.Frame(notebook, padding=12)
        notebook.add(setup_frame, text="Setup")
        notebook.add(run_frame, text="Run Monitor")
        notebook.add(review_frame, text="Review Queue")

        self._build_setup_tab(setup_frame)
        self._build_run_tab(run_frame)
        self._build_review_tab(review_frame)

    def _build_setup_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=(0, 0, 12, 0))
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.bind("<Enter>", self._bind_setup_mousewheel, add="+")
        canvas.bind("<Leave>", self._unbind_setup_mousewheel, add="+")
        inner.bind("<Enter>", self._bind_setup_mousewheel, add="+")
        inner.bind("<Leave>", self._unbind_setup_mousewheel, add="+")
        self.setup_canvas = canvas

        frame = inner
        frame.columnconfigure(2, weight=1)
        labels = [
            ("Resume source", self.resume_var),
            ("Job keyword", self.keyword_var),
            ("Location", self.location_var),
            ("Include titles", self.include_titles_var),
            ("Exclude titles", self.exclude_titles_var),
            ("Salary floor", self.salary_floor_var),
            ("Force escalate keywords", self.force_keywords_var),
            ("Source provider", self.source_provider_var),
            ("JobSpy sites", self.jobspy_sites_var),
            ("Results per page", self.results_per_page_var),
            ("USAJobs account email", self.usajobs_email_var),
            ("USAJobs authorization key", self.usajobs_auth_key_var),
            ("Adzuna app id", self.adzuna_app_id_var),
            ("Adzuna app key", self.adzuna_app_key_var),
            ("Adzuna country", self.adzuna_country_var),
            ("Automation mode", self.automation_mode_var),
            ("Cheap stage provider", self.cheap_stage_provider_var),
            ("Cheap stage model", self.cheap_stage_model_var),
            ("Review threshold", self.threshold_var),
            ("Final apply threshold", self.final_apply_threshold_var),
            ("Cheap reject threshold", self.cheap_reject_threshold_var),
            ("Cheap escalate threshold", self.cheap_escalate_threshold_var),
            ("Pre-cheap reject threshold", self.precheap_gate_threshold_var),
            ("Fast rank min score", self.fast_rank_min_score_var),
            ("Cheap AI top N", self.cheap_ai_top_n_var),
            ("Strong AI top N", self.strong_ai_top_n_var),
            ("Strong stage provider", self.strong_stage_provider_var),
            ("Strong stage model", self.strong_stage_model_var),
            ("Doc stage provider", self.doc_stage_provider_var),
            ("Doc stage model", self.doc_stage_model_var),
            ("Ollama base URL", self.ollama_base_url_var),
            ("Anthropic API key", self.anthropic_api_key_var),
            ("OpenAI API key", self.openai_api_key_var),
            ("Gmail sender", self.sender_var),
            ("Gmail recipient (optional fallback/test inbox)", self.recipient_var),
            ("Client secrets path", self.client_secret_var),
        ]
        values_map = {
            "Source provider": ("jobspy", "adzuna", "usajobs"),
            "Automation mode": ("semi_auto", "auto"),
            "Cheap stage provider": ("ollama_local", "openai", "anthropic"),
            "Strong stage provider": ("anthropic", "openai"),
            "Doc stage provider": ("openai", "anthropic", "ollama_local"),
        }
        for idx, (label, var) in enumerate(labels):
            label_widget = ttk.Label(frame, text=label)
            label_widget.grid(row=idx, column=0, sticky="w", pady=6, padx=(0, 10))
            self._add_tooltip(label_widget, FIELD_TOOLTIPS.get(label, label))
            if label == "Resume source":
                action_frame = ttk.Frame(frame)
                action_frame.grid(row=idx, column=1, sticky="w", pady=6, padx=(0, 10))
                open_button = ttk.Button(action_frame, text="Open Resume", command=self._open_resume_source)
                open_button.pack(side="left", padx=(0, 8))
                browse_button = ttk.Button(action_frame, text="Browse Resume", command=self._browse_resume)
                browse_button.pack(side="left")
                self._add_tooltip(open_button, "Open the configured source resume file from disk.")
                self._add_tooltip(browse_button, "Choose a resume file to use as the source document.")
                entry = ttk.Entry(frame, textvariable=var, width=70)
                entry.grid(row=idx, column=2, sticky="ew", pady=6)
                self._bind_entry_autosave(entry)
                self._add_tooltip(entry, FIELD_TOOLTIPS[label])
            elif label == "Client secrets path":
                action_frame = ttk.Frame(frame)
                action_frame.grid(row=idx, column=1, sticky="w", pady=6, padx=(0, 10))
                browse_button = ttk.Button(action_frame, text="Browse", command=self._browse_client_secrets)
                browse_button.pack(side="left")
                self._add_tooltip(browse_button, "Choose your Google OAuth client secrets JSON file.")
                entry = ttk.Entry(frame, textvariable=var, width=70)
                entry.grid(row=idx, column=2, sticky="ew", pady=6)
                self._bind_entry_autosave(entry)
                self._add_tooltip(entry, FIELD_TOOLTIPS[label])
            elif label == "Job keyword":
                action_frame = ttk.Frame(frame)
                action_frame.grid(row=idx, column=1, sticky="w", pady=6, padx=(0, 10))
                fit_button = ttk.Button(action_frame, text="Fit to Resume", command=self._fit_to_resume)
                fit_button.pack(side="left")
                self.fit_resume_button = fit_button
                self._add_tooltip(fit_button, FIELD_TOOLTIPS["Fit to Resume"])
                entry = ttk.Entry(frame, textvariable=var, width=70)
                entry.grid(row=idx, column=2, sticky="ew", pady=6)
                self._bind_entry_autosave(entry)
                self._add_tooltip(entry, FIELD_TOOLTIPS[label])
            elif label in {"Source provider", "Automation mode", "Cheap stage provider", "Strong stage provider", "Doc stage provider"}:
                combo = ttk.Combobox(frame, textvariable=var, values=values_map[label], state="readonly", width=67)
                combo.grid(row=idx, column=1, columnspan=2, sticky="ew", pady=6)
                if label == "Source provider":
                    combo.bind("<<ComboboxSelected>>", self._on_source_provider_changed, add="+")
                if label == "Cheap stage provider":
                    combo.bind("<<ComboboxSelected>>", self._on_cheap_provider_changed, add="+")
                if label == "Strong stage provider":
                    combo.bind("<<ComboboxSelected>>", self._on_strong_provider_changed, add="+")
                if label == "Doc stage provider":
                    combo.bind("<<ComboboxSelected>>", self._on_doc_provider_changed, add="+")
                if label == "Automation mode":
                    combo.bind("<<ComboboxSelected>>", self._on_automation_mode_changed, add="+")
                combo.bind("<<ComboboxSelected>>", self._autosave_setup, add="+")
                self._add_tooltip(combo, FIELD_TOOLTIPS[label])
            elif label in {"Cheap stage model", "Strong stage model", "Doc stage model"}:
                combo = ttk.Combobox(frame, textvariable=var, state="readonly", width=67)
                combo.grid(row=idx, column=1, columnspan=2, sticky="ew", pady=6)
                combo.bind("<<ComboboxSelected>>", self._autosave_setup, add="+")
                if label == "Cheap stage model":
                    self.cheap_stage_model_combo = combo
                elif label == "Strong stage model":
                    self.strong_stage_model_combo = combo
                else:
                    self.doc_stage_model_combo = combo
                self._add_tooltip(combo, FIELD_TOOLTIPS[label])
            else:
                show = "*" if label in {"Anthropic API key", "OpenAI API key", "USAJobs authorization key", "Adzuna app key"} else ""
                entry = ttk.Entry(frame, textvariable=var, width=70, show=show)
                entry.grid(row=idx, column=1, columnspan=2, sticky="ew", pady=6)
                self._bind_entry_autosave(entry)
                self._add_tooltip(entry, FIELD_TOOLTIPS[label])

        self._sync_cheap_model_dropdown()
        self._sync_strong_model_dropdown()
        self._sync_doc_model_dropdown()

        check = ttk.Checkbutton(frame, text="Enable Gmail delivery", variable=self.gmail_enabled_var, command=self._autosave_setup)
        check.grid(row=len(labels), column=1, columnspan=2, sticky="w", pady=6)
        self._add_tooltip(check, FIELD_TOOLTIPS["Enable Gmail delivery"])
        skip_ai_check = ttk.Checkbutton(frame, text="Skip AI scoring in semi_auto", variable=self.skip_ai_scoring_var, command=self._autosave_setup)
        skip_ai_check.grid(row=len(labels) + 1, column=1, columnspan=2, sticky="w", pady=6)
        self._add_tooltip(skip_ai_check, FIELD_TOOLTIPS["Skip AI scoring in semi_auto"])
        progressive_check = ttk.Checkbutton(frame, text="Enable progressive queue", variable=self.progressive_queue_enabled_var, command=self._autosave_setup)
        progressive_check.grid(row=len(labels) + 2, column=1, columnspan=2, sticky="w", pady=6)
        self._add_tooltip(progressive_check, FIELD_TOOLTIPS["Enable progressive queue"])
        precheap_check = ttk.Checkbutton(frame, text="Enable pre-cheap gate", variable=self.precheap_gate_enabled_var, command=self._autosave_setup)
        precheap_check.grid(row=len(labels) + 3, column=1, columnspan=2, sticky="w", pady=6)
        self._add_tooltip(precheap_check, FIELD_TOOLTIPS["Enable pre-cheap gate"])
        portal_row = ttk.Frame(frame)
        portal_row.grid(row=len(labels) + 4, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        portal_row.columnconfigure(0, weight=1)
        portal_status = ttk.Label(portal_row, textvariable=self.portal_readiness_var)
        portal_status.grid(row=0, column=0, sticky="w")
        self._add_tooltip(portal_status, "Shows whether browser-based portal autofill is available on this machine.")
        portal_test_button = ttk.Button(portal_row, text="Test Portal Runtime", command=self._test_portal_autofill_runtime)
        portal_test_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.portal_test_buttons.append(portal_test_button)
        self._add_tooltip(portal_test_button, "Run an in-app headless Chromium launch check and report the exact portal runtime readiness.")
        gmail_status = ttk.Label(frame, textvariable=self.gmail_readiness_var)
        gmail_status.grid(row=len(labels) + 5, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self._add_tooltip(gmail_status, "Shows whether Gmail email sending looks configured before you try Approve and Send on email jobs.")

    def _build_run_tab(self, frame: ttk.Frame) -> None:
        top = ttk.Frame(frame)
        top.pack(fill="x")
        run_button = ttk.Button(top, text="Run Now", command=self._run_now)
        run_button.pack(side="left")
        self._add_tooltip(run_button, "Run the scrape, scoring, document generation, and delivery pipeline now.")
        status_label = ttk.Label(top, textvariable=self.status_var)
        status_label.pack(side="left", padx=12)
        self._add_tooltip(status_label, "Current app status, including autosave and run results.")
        self.last_run_label = ttk.Label(top, text="No runs yet")
        self.last_run_label.pack(side="left", padx=12)
        self._add_tooltip(self.last_run_label, "Summary of the most recent pipeline run.")

        log_frame = ttk.Frame(frame)
        log_frame.pack(fill="both", expand=True, pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=30, wrap="word")
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self._add_tooltip(self.log_text, "Recent application logs from the current workspace.")
        self.cost_text = tk.Text(frame, height=8, wrap="word")
        self.cost_text.pack(fill="x", expand=False, pady=(12, 0))
        self._add_tooltip(self.cost_text, "Tracked estimated API costs by stage.")

    def _build_review_tab(self, frame: ttk.Frame) -> None:
        columns = ("title", "employer", "posted_at", "score", "score_source", "verification_stage", "hr_email", "document_status", "delivery_status")
        tree_container = ttk.Frame(frame)
        tree_container.pack(fill="both", expand=True)
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)

        tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=18)
        for column in columns:
            heading_text = "HR Email" if column == "hr_email" else column.replace("_", " ").title()
            tree.heading(column, text=heading_text, command=lambda col=column: self._sort_review_rows(col))
            tree.column(column, width=150, anchor="w")
        tree.column("title", width=250)
        tree.column("employer", width=180)
        tree.column("posted_at", width=150)
        tree.column("score_source", width=110)
        tree.column("verification_stage", width=125)
        tree.column("hr_email", width=90, anchor="center")
        review_scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=review_scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        review_scrollbar.grid(row=0, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_selected_details())
        self.review_tree = tree
        self._add_tooltip(tree, "Jobs awaiting review, approval, or delivery follow-up.")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        refresh_button = ttk.Button(buttons, text="Refresh", command=self._refresh_review_queue_action)
        refresh_button.pack(side="left")
        self._add_tooltip(refresh_button, "Reload the queue, logs, run summary, and selected job details.")
        apply_button = ttk.Button(buttons, text="Open Apply Link", command=self._open_apply_link)
        apply_button.pack(side="left", padx=8)
        self._add_tooltip(apply_button, "Open the job posting or application page in your browser.")
        generate_button = ttk.Button(buttons, text="Generate", command=self._generate_documents_for_selected)
        generate_button.pack(side="left")
        self._add_tooltip(generate_button, "Generate the tailored resume and cover letter for the selected review item.")
        self.generate_button = generate_button
        open_resume_button = ttk.Button(buttons, text="Open Resume", command=self._open_resume)
        open_resume_button.pack(side="left", padx=8)
        self._add_tooltip(open_resume_button, "Open the generated tailored resume for the selected review item, preferring DOCX when available.")
        open_cover_button = ttk.Button(buttons, text="Open Cover Letter", command=self._open_cover_letter)
        open_cover_button.pack(side="left")
        self._add_tooltip(open_cover_button, "Open the generated cover letter for the selected review item.")
        approve_button = ttk.Button(buttons, text="Approve and Send", command=self._approve_and_send)
        approve_button.pack(side="left", padx=8)
        self._add_tooltip(approve_button, "Send the selected job through the configured delivery path.")
        self.approve_button = approve_button
        review_portal_test_button = ttk.Button(buttons, text="Test Portal Runtime", command=self._test_portal_autofill_runtime)
        review_portal_test_button.pack(side="left")
        self.portal_test_buttons.append(review_portal_test_button)
        self._add_tooltip(review_portal_test_button, "Run a portal runtime verification using the current desktop app session.")

        outcome_frame = ttk.Frame(buttons)
        outcome_frame.pack(side="left", padx=(12, 0))
        outcome_options = ("no_response", "rejected", "phone_screen", "interview", "offer", "withdrew")
        outcome_combo = ttk.Combobox(outcome_frame, textvariable=self.outcome_var, values=outcome_options, width=14, state="readonly")
        outcome_combo.pack(side="left")
        outcome_button = ttk.Button(outcome_frame, text="Record Outcome", command=self._record_outcome)
        outcome_button.pack(side="left", padx=(4, 0))
        self._add_tooltip(outcome_combo, "Select what happened after this application was sent.")
        self._add_tooltip(outcome_button, "Record the outcome for the selected job. Used to track your application success rate.")

        portal_status = ttk.Label(buttons, textvariable=self.portal_readiness_var)
        portal_status.pack(side="left", padx=(12, 0))
        self._add_tooltip(portal_status, "Shows whether browser-based portal autofill is available on this machine.")
        gmail_status = ttk.Label(buttons, textvariable=self.gmail_readiness_var)
        gmail_status.pack(side="left", padx=(12, 0))
        self._add_tooltip(gmail_status, "Shows whether Gmail email sending looks configured before you try Approve and Send on email jobs.")

        progress_frame = ttk.Frame(frame)
        progress_frame.pack(fill="x", pady=(8, 0))
        progress_frame.columnconfigure(0, weight=1)
        progress_bar = ttk.Progressbar(progress_frame, maximum=8, variable=self.generate_progress_var)
        progress_bar.grid(row=0, column=0, sticky="ew")
        self.generate_progressbar = progress_bar
        self._add_tooltip(progress_bar, "Shows progress for the current Review Queue action, including Generate and Approve and Send.")
        ttk.Label(progress_frame, textvariable=self.generate_status_var).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(progress_frame, textvariable=self.generate_context_var).grid(row=2, column=0, sticky="w")

        self.details_text = tk.Text(frame, height=16, wrap="word")
        self.details_text.pack(fill="both", expand=False, pady=(10, 0))
        self._add_tooltip(self.details_text, "Detailed view of the selected job, generated files, and delivery status.")

    def _browse_resume(self) -> None:
        path = filedialog.askopenfilename(
            title="Select resume source",
            filetypes=[("Resume files", "*.docx *.pdf *.txt"), ("All files", "*.*")],
        )
        if path:
            self.resume_var.set(path)
            self._autosave_setup()

    def _browse_client_secrets(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Google client secrets file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.client_secret_var.set(path)
            self._autosave_setup()

    def _open_resume_source(self) -> None:
        configured_path = self.resume_var.get().strip()
        if not configured_path:
            messagebox.showwarning("Job Bot", "No source resume is configured yet.")
            return
        path = self._resolve_configured_path(configured_path)
        if not path.exists():
            messagebox.showwarning("Job Bot", f"Configured resume source was not found:\n{path}")
            return
        os.startfile(str(path))

    def _fit_to_resume(self) -> None:
        configured_path = self.resume_var.get().strip()
        if not configured_path:
            messagebox.showwarning("Job Bot", "Configure Resume source before using Fit to Resume.")
            return
        try:
            self._build_config_from_vars()
        except Exception as exc:
            messagebox.showwarning("Job Bot", f"Current setup values need attention before fitting to resume:\n{exc}")
            return
        self.status_var.set("Generating job keywords from resume...")
        self._set_fit_resume_button_enabled(False)
        thread = threading.Thread(target=self._fit_to_resume_background, daemon=True)
        thread.start()

    def _fit_to_resume_background(self) -> None:
        try:
            config = self._build_config_from_vars()
            resume_path = self._resolve_configured_path(config.resume_source_path)
            if not resume_path.exists():
                raise FileNotFoundError(f"Configured resume source was not found: {resume_path}")
            resume_data = parse_resume(resume_path, self.paths.resume_json)
            keywords = MatchScorer(config, self.database).suggest_job_keywords(resume_data)
        except Exception as exc:
            self.root.after(0, lambda: self._handle_fit_to_resume_error(str(exc)))
            return
        self.root.after(0, lambda: self._apply_fit_to_resume_keywords(keywords))

    def _apply_fit_to_resume_keywords(self, keywords: str) -> None:
        self.keyword_var.set(keywords)
        if self._autosave_setup():
            self.status_var.set("Resume-fit keywords generated. Review and edit them before running.")
        self._set_fit_resume_button_enabled(True)

    def _handle_fit_to_resume_error(self, message: str) -> None:
        self.status_var.set(f"Fit to Resume failed: {message}")
        self._set_fit_resume_button_enabled(True)

    def _set_fit_resume_button_enabled(self, enabled: bool) -> None:
        if self.fit_resume_button:
            self.fit_resume_button.configure(state="normal" if enabled else "disabled")

    def _resolve_configured_path(self, configured_path: str) -> Path:
        path = Path(configured_path).expanduser()
        if path.is_absolute():
            return path
        return (self.paths.root / path).resolve()

    def _bind_entry_autosave(self, widget: ttk.Entry) -> None:
        widget.bind("<FocusOut>", self._autosave_setup, add="+")

    def _bind_setup_mousewheel(self, _event: object | None = None) -> None:
        self.root.bind_all("<MouseWheel>", self._on_setup_mousewheel, add="+")

    def _unbind_setup_mousewheel(self, _event: object | None = None) -> None:
        self.root.unbind_all("<MouseWheel>")

    def _on_setup_mousewheel(self, event: tk.Event) -> None:
        if self.setup_canvas:
            self.setup_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_strong_provider_changed(self, _event: object | None = None) -> None:
        self._sync_strong_model_dropdown()

    def _on_cheap_provider_changed(self, _event: object | None = None) -> None:
        self._sync_cheap_model_dropdown()

    def _on_doc_provider_changed(self, _event: object | None = None) -> None:
        self._sync_doc_model_dropdown()

    def _on_source_provider_changed(self, _event: object | None = None) -> None:
        self._source_provider_user_set = True

    def _on_automation_mode_changed(self, _event: object | None = None) -> None:
        mode = self.automation_mode_var.get().strip() or "semi_auto"
        self.results_per_page_var.set("100" if mode == "semi_auto" else "25")
        if not self._source_provider_user_set:
            default_provider = "jobspy" if mode == "semi_auto" else "adzuna"
            self.source_provider_var.set(default_provider)
        if mode == "auto" and not self.location_var.get().strip():
            self.location_var.set("New York, NY")

    def _sync_cheap_model_dropdown(self) -> None:
        if not self.cheap_stage_model_combo:
            return
        provider = self.cheap_stage_provider_var.get().strip() or "openai"
        models = MODEL_OPTIONS.get(provider, ())
        self.cheap_stage_model_combo.configure(values=models)
        current = self.cheap_stage_model_var.get().strip()
        if current not in models and models:
            self.cheap_stage_model_var.set(models[0])

    def _sync_strong_model_dropdown(self) -> None:
        if not self.strong_stage_model_combo:
            return
        provider = self.strong_stage_provider_var.get().strip() or "anthropic"
        models = MODEL_OPTIONS.get(provider, ())
        self.strong_stage_model_combo.configure(values=models)
        current = self.strong_stage_model_var.get().strip()
        if current not in models and models:
            self.strong_stage_model_var.set(models[0])

    def _sync_doc_model_dropdown(self) -> None:
        if not self.doc_stage_model_combo:
            return
        provider = self.doc_stage_provider_var.get().strip() or "openai"
        models = MODEL_OPTIONS.get(provider, ())
        self.doc_stage_model_combo.configure(values=models)
        current = self.doc_stage_model_var.get().strip()
        if current not in models and models:
            self.doc_stage_model_var.set(models[0])

    def _autosave_setup(self, _event: object | None = None) -> bool:
        return self._save_config(show_status_only=True)

    def _save_config(self, show_status_only: bool = True) -> bool:
        try:
            updated_config = self._build_config_from_vars()
            save_config(updated_config, self.paths.config_file)
            self.config = updated_config
            self.pipeline = JobBotPipeline(self.config, self.paths, self.database)
            self._refresh_portal_readiness()
            self._refresh_gmail_readiness()
            if show_status_only:
                self.status_var.set("Settings saved.")
            return True
        except Exception as exc:
            self.status_var.set(f"Settings not saved: {exc}")
            return False

    def _build_config_from_vars(self) -> JobBotConfig:
        config = copy.deepcopy(self.config)
        config.resume_source_path = self.resume_var.get().strip()
        config.llm_provider = "anthropic"
        config.cheap_stage_provider = self.cheap_stage_provider_var.get().strip() or "ollama_local"
        config.cheap_stage_model = self.cheap_stage_model_var.get().strip() or "qwen2.5:7b"
        config.strong_stage_provider = self.strong_stage_provider_var.get().strip() or "anthropic"
        config.strong_stage_model = self.strong_stage_model_var.get().strip() or "claude-sonnet-4-20250514"
        config.doc_stage_provider = self.doc_stage_provider_var.get().strip() or "openai"
        config.doc_stage_model = self.doc_stage_model_var.get().strip() or "gpt-5-mini"
        config.ollama_base_url = self.ollama_base_url_var.get().strip() or "http://localhost:11434"
        config.anthropic_api_key = self.anthropic_api_key_var.get().strip()
        config.openai_api_key = self.openai_api_key_var.get().strip()
        config.source.keyword = self.keyword_var.get().strip()
        config.source.location = self.location_var.get().strip()
        config.source.provider = self.source_provider_var.get().strip() or ("jobspy" if config.automation_mode == "semi_auto" else "adzuna")
        config.source.jobspy_sites = self._parse_csv(self.jobspy_sites_var.get()) or ["indeed", "google"]
        config.automation_mode = self.automation_mode_var.get().strip() or "semi_auto"
        config.source.results_per_page = int(self.results_per_page_var.get().strip() or ("100" if config.automation_mode == "semi_auto" else "25"))
        config.source.user_agent = self.usajobs_email_var.get().strip() or "jobbot-demo@example.com"
        config.source.authorization_key = self.usajobs_auth_key_var.get().strip()
        config.source.adzuna_app_id = self.adzuna_app_id_var.get().strip()
        config.source.adzuna_app_key = self.adzuna_app_key_var.get().strip()
        config.source.adzuna_country = self.adzuna_country_var.get().strip() or "us"
        config.include_titles = self._parse_csv(self.include_titles_var.get())
        config.exclude_titles = self._parse_csv(self.exclude_titles_var.get())
        config.force_escalate_keywords = self._parse_csv(self.force_keywords_var.get())
        config.salary_floor = int(self.salary_floor_var.get().strip() or "0")
        config.scoring_threshold = int(self.threshold_var.get().strip() or "70")
        config.final_apply_threshold = int(self.final_apply_threshold_var.get().strip() or "80")
        config.cheap_reject_threshold = int(self.cheap_reject_threshold_var.get().strip() or "55")
        config.cheap_escalate_threshold = int(self.cheap_escalate_threshold_var.get().strip() or "75")
        config.precheap_gate_reject_threshold = int(self.precheap_gate_threshold_var.get().strip() or "30")
        config.fast_rank_min_score = int(self.fast_rank_min_score_var.get().strip() or "35")
        config.cheap_ai_top_n = int(self.cheap_ai_top_n_var.get().strip() or "20")
        config.strong_ai_top_n = int(self.strong_ai_top_n_var.get().strip() or "7")
        config.skip_ai_scoring_in_semi_auto = self.skip_ai_scoring_var.get()
        config.progressive_queue_enabled = self.progressive_queue_enabled_var.get()
        config.precheap_gate_enabled = self.precheap_gate_enabled_var.get()
        config.gmail.enabled = self.gmail_enabled_var.get()
        config.gmail.recipient_email = self.recipient_var.get().strip()
        config.gmail.sender_email = self.sender_var.get().strip()
        config.gmail.client_secrets_file = self.client_secret_var.get().strip()
        return config

    def _run_now(self) -> None:
        if self.config.automation_mode == "auto" and not self._confirm_auto_run():
            self.status_var.set("Auto run canceled.")
            return
        self._run_in_progress = True
        self.status_var.set("Starting run...")
        self._start_run_polling()
        thread = threading.Thread(target=self._run_pipeline_background, daemon=True)
        thread.start()

    def _confirm_auto_run(self) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("Confirm Automatic Run")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()

        confirmed = {"value": False}

        container = ttk.Frame(dialog, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Auto mode is enabled. Running now may send applications automatically.",
            wraplength=380,
            justify="left",
        ).pack(anchor="w")

        ttk.Label(
            container,
            text="Click 'Run automatically' to continue, or Cancel to go back.",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        buttons = ttk.Frame(container)
        buttons.pack(anchor="e", pady=(16, 0))

        def close_with(value: bool) -> None:
            confirmed["value"] = value
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=lambda: close_with(False)).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Run automatically", command=lambda: close_with(True)).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", lambda: close_with(False))
        self.root.wait_window(dialog)
        return confirmed["value"]

    def _confirm_approve_and_send(self, row: dict[str, object]) -> bool:
        heading, detail, action_label = self._approve_and_send_confirmation_copy(row)
        dialog = tk.Toplevel(self.root)
        dialog.title("Confirm Approve and Send")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()

        confirmed = {"value": False}
        container = ttk.Frame(dialog, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text=heading, wraplength=420, justify="left").pack(anchor="w")
        ttk.Label(container, text=detail, wraplength=420, justify="left").pack(anchor="w", pady=(8, 0))

        buttons = ttk.Frame(container)
        buttons.pack(anchor="e", pady=(16, 0))

        def close_with(value: bool) -> None:
            confirmed["value"] = value
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=lambda: close_with(False)).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text=action_label, command=lambda: close_with(True)).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", lambda: close_with(False))
        self.root.wait_window(dialog)
        return confirmed["value"]

    def _approve_and_send_confirmation_copy(self, row: dict[str, object]) -> tuple[str, str, str]:
        title = str(row.get("title") or "this role")
        employer = str(row.get("employer") or "this employer")
        apply_method = str(row.get("apply_method") or "")
        if apply_method == "email":
            assessment = self._email_apply_assessment_for_row(row)
            destination = assessment.email or str(row.get("hiring_manager_email") or "the detected HR email")
            if not assessment.is_explicit:
                return (
                    f"HR email sending is blocked for {title} at {employer}.",
                    f"JobBot will not send to {destination}. {assessment.reason}",
                    "Continue",
                )
            return (
                f"You are about to send an application email for {title} at {employer}.",
                f"This will send the generated resume and cover letter to {destination}. Make sure the documents look right before continuing.",
                "Send application",
            )
        readiness = self._portal_readiness_for_row(row)
        if readiness.lower() == "ready":
            return (
                f"You are about to start the assisted apply flow for {title} at {employer}.",
                "JobBot will attempt supported portal autofill first. If the portal is blocked by login, CAPTCHA, or an unsupported flow, it will open the apply page for you to finish manually.",
                "Attempt apply",
            )
        return (
            f"You are about to open the apply page for {title} at {employer}.",
            f"Portal autofill is not currently available ({readiness}). JobBot will open the application page for manual completion and leave your generated documents ready on disk.",
            "Open apply page",
        )

    def _run_pipeline_background(self) -> None:
        result = self.pipeline.run()
        self.root.after(
            0,
            lambda: (
                setattr(self, "_run_in_progress", False),
                self._stop_run_polling(),
                self.status_var.set(f"{result.status} - {result.message} - est. cost ${result.estimated_cost_usd:.4f}"),
                self.refresh_view(),
            ),
        )

    def _start_run_polling(self) -> None:
        self._stop_run_polling()
        self._poll_run_progress()

    def _stop_run_polling(self) -> None:
        if self._run_poll_after_id:
            self.root.after_cancel(self._run_poll_after_id)
            self._run_poll_after_id = None

    def _poll_run_progress(self) -> None:
        run = self.database.latest_run()
        if run and run.get("status") == "running":
            message = run.get("message") or "Working..."
            stage = run.get("stage") or "running"
            seen = run.get("jobs_seen") or 0
            matched = run.get("jobs_matched") or 0
            self.status_var.set(f"Running - {stage}: {message} | seen={seen} matched={matched}")
            self.refresh_view()
            self._run_poll_after_id = self.root.after(1000, self._poll_run_progress)
        elif self._run_in_progress:
            self.status_var.set("Running - starting: Initializing run... | seen=0 matched=0")
            self.refresh_view()
            self._run_poll_after_id = self.root.after(500, self._poll_run_progress)
        else:
            self._run_poll_after_id = None

    def refresh_view(self) -> None:
        self._refresh_portal_readiness()
        self._refresh_gmail_readiness()
        self._refresh_logs()
        self._refresh_costs()
        self._refresh_runs()
        self._refresh_review_queue()
        self._refresh_selected_details()

    def _refresh_review_queue_action(self) -> None:
        self.refresh_view()
        row_count = len(self._review_rows)
        noun = "job" if row_count == 1 else "jobs"
        self.status_var.set(f"Review Queue refreshed: {row_count} {noun} loaded.")

    def _refresh_logs(self) -> None:
        if not self.log_text:
            return
        content = ""
        if self.paths.log_file.exists():
            content = self.paths.log_file.read_text(encoding="utf-8", errors="ignore")[-8000:]
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", content or "No logs yet.")
        self.log_text.see(tk.END)

    def _refresh_runs(self) -> None:
        run = self.database.latest_run()
        if self.last_run_label:
            if not run:
                self.last_run_label.config(text="No runs yet")
            else:
                self.last_run_label.config(
                    text=f"Last run: {run['status']} | stage={run['stage']} | seen={run['jobs_seen']} matched={run['jobs_matched']}"
                )

    def _record_outcome(self) -> None:
        row = self._selected_row()
        if not row:
            return
        outcome = self.outcome_var.get().strip()
        if not outcome:
            messagebox.showwarning("Job Bot", "Select an outcome before recording.")
            return
        self.database.record_outcome(str(row["id"]), outcome)
        self.status_var.set(f"Outcome recorded: {outcome} for {row['title']} at {row['employer']}")
        self._refresh_costs()

    def _refresh_costs(self) -> None:
        if not self.cost_text:
            return
        rows = self.database.summarize_costs()
        total = sum(float(row.get("total_cost") or 0.0) for row in rows)
        lines = [f"Estimated AI cost tracked so far: ${total:.4f}", ""]
        for row in rows:
            lines.append(f"{row['stage_name']}: {row['evaluations']} evals, ${float(row.get('total_cost') or 0.0):.4f}")
        if len(lines) == 2:
            lines.append("No API cost data recorded yet.")
        lines.append("")
        summary = self.database.get_outcomes_summary()
        lines.append(f"Application outcomes: {summary['total_applied']} applied, {summary['total_with_outcome']} tracked")
        if summary["total_with_outcome"] > 0:
            lines.append(f"Response rate: {summary['response_rate_pct']}% (phone screen / interview / offer)")
            by_outcome = summary["by_outcome"]
            for label in ("no_response", "rejected", "phone_screen", "interview", "offer", "withdrew"):
                count = by_outcome.get(label, 0)
                if count:
                    lines.append(f"  {label}: {count}")
        self.cost_text.delete("1.0", tk.END)
        self.cost_text.insert("1.0", "\n".join(lines))

    def _refresh_review_queue(self) -> None:
        if not self.review_tree:
            return
        self._review_rows = self.database.list_review_rows()
        self._populate_review_tree()

    def _populate_review_tree(self) -> None:
        if not self.review_tree:
            return
        selected = self.review_tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        for row in self._sorted_review_rows():
            self.review_tree.insert(
                "",
                "end",
                iid=row["id"],
                values=(
                    row["title"],
                    row["employer"],
                    self._format_posted_at(str(row.get("posted_at") or "")),
                    row["score"],
                    row.get("score_source") or row["source"],
                    row.get("verification_stage") or "",
                    self._hr_email_status(row),
                    row["document_status"],
                    row["delivery_status"],
                ),
            )
        if selected_id and self.review_tree.exists(selected_id):
            self.review_tree.selection_set(selected_id)

    def _sorted_review_rows(self) -> list[dict[str, object]]:
        def sort_value(row: dict[str, object]) -> object:
            value = row.get(self._review_sort_column)
            if self._review_sort_column == "score":
                return int(value or 0)
            if self._review_sort_column == "hr_email":
                return self._hr_email_status(row)
            return str(value or "").lower()

        return sorted(self._review_rows, key=sort_value, reverse=self._review_sort_desc)

    def _sort_review_rows(self, column: str) -> None:
        if self._review_sort_column == column:
            self._review_sort_desc = not self._review_sort_desc
        else:
            self._review_sort_column = column
            self._review_sort_desc = column in {"score", "posted_at"}
        self._populate_review_tree()

    @staticmethod
    def _format_posted_at(value: str) -> str:
        if not value:
            return ""
        return value.replace("T", " ")[:19]

    @staticmethod
    def _format_generated_at(value: str) -> str:
        if not value:
            return ""
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %I:%M:%S %p")
        except ValueError:
            return value.replace("T", " ")[:19]

    def _refresh_selected_details(self) -> None:
        if not self.details_text:
            return
        row = self._selected_row(show_warning=False)
        if not row:
            self.details_text.delete("1.0", tk.END)
            self.details_text.insert("1.0", "Select a job to review its description, match notes, and generated files.")
            return
        email_assessment = self._email_apply_assessment_for_row(row)
        details = "\n".join(
            [
                f"Title: {row['title']}",
                f"Employer: {row['employer']}",
                f"Location: {row['location']}",
                f"Posted at: {self._format_posted_at(row['posted_at']) or 'Unknown'}",
                f"Source: {row['source']}",
                f"Resume source type: {Path(self.config.resume_source_path).suffix.lower() or 'unknown'}",
                f"Score: {row['score']}",
                f"Score source: {row.get('score_source') or 'unknown'}",
                f"Verification stage: {row.get('verification_stage') or 'unknown'}",
                f"Provisional rank: {row.get('provisional_rank') or 'n/a'}",
                f"Match status: {row['match_status']}",
                f"Apply method: {row['apply_method']}",
                f"HR email: {email_assessment.confidence}",
                f"Portal autofill readiness: {self._portal_readiness_for_row(row)}",
                f"HR email destination: {row['hiring_manager_email'] or 'Not present'}",
                f"Delivery status: {row['delivery_status']}",
                f"Delivery method: {row['delivery_method']}",
                f"Apply URL: {row['apply_url']}",
                f"Delivery detail: {row['delivery_error'] or 'None'}",
                f"HR email review: {email_assessment.reason}",
                "",
                "Match rationale:",
                row["rationale"] or "No rationale available.",
                "",
                "Generated resume (DOCX):",
                self._document_status_text(row.get("resume_docx_path", "")),
                "",
                "Generated resume (PDF):",
                self._document_status_text(row["resume_pdf_path"]),
                "",
                "Generated cover letter (DOCX):",
                self._document_status_text(row.get("cover_letter_docx_path", "")),
                "",
                "Generated cover letter (PDF):",
                self._document_status_text(row.get("cover_letter_pdf_path", "")),
                "",
                f"Document status: {row['document_status']}",
                f"Generated at: {self._format_generated_at(str(row.get('generated_at') or '')) or 'Not generated'}",
                f"Document error: {row.get('document_error') or 'None'}",
                "",
                "--- Doc generation log ---",
                f"Tailoring route:    {row.get('tailoring_route') or 'N/A'}",
                f"Provider / model:   {(row.get('tailoring_provider') or '') + ('/' + row.get('tailoring_model') if row.get('tailoring_model') else '') or 'N/A (local)'}",
                f"AI attempted:       {'Yes' if self._doc_ai_attempted(row) else 'No'}",
                f"AI accepted:        {'Yes' if row.get('tailoring_route') == 'openai' else ('*** FELL BACK TO LOCAL HEURISTICS — cover letter and resume may be less tailored ***' if row.get('tailoring_route') == 'fallback' else 'N/A')}",
                f"Resume AI accepted: {self._doc_section_status(str(row.get('resume_ai_status') or ''))}",
                f"Cover letter AI accepted: {self._doc_section_status(str(row.get('cover_letter_ai_status') or ''))}",
                f"Rejected bullets repaired: {row.get('rejected_bullets_repaired', 0)}",
                f"Cover letter fallback: {row.get('cover_letter_fallback') or 'None'}",
                f"Fallback reason:    {row.get('tailoring_fallback_reason') or 'None'}",
                f"AI retry count:     {row.get('tailoring_retry_count', 0)}",
                f"AI validation attempts: {row.get('ai_validation_attempts', 0)}",
                f"Resume retry performed: {'Yes' if int(row.get('resume_retry_performed') or 0) else 'No'}",
                f"Cover letter retry performed: {'Yes' if int(row.get('cover_letter_retry_performed') or 0) else 'No'}",
                f"AI repair applied:  {'Yes' if int(row.get('ai_repair_applied') or 0) else 'No'}",
                f"Page-fit attempts:  {row.get('page_fit_attempts', 0)}",
                f"PDF exporter:       {row.get('pdf_exporter_used') or 'N/A'}",
                "",
                "--- Approval log ---",
                row.get("approval_log") or "No approval attempt recorded yet.",
                "",
                "--- Cover letter quality check ---",
            ]
            + self._cover_letter_quality_lines(row)
            + [
                "",
                "--- Application outcome ---",
                self._outcome_line(str(row["id"])),
                "",
                "Job description:",
                row["description_full"] or "No description captured.",
            ]
        )
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", details)

    def _selected_row(self, show_warning: bool = True):
        if not self.review_tree:
            return None
        selected = self.review_tree.selection()
        if not selected:
            if show_warning:
                messagebox.showwarning("Job Bot", "Select a review item first.")
            return None
        return self.database.get_review_row(selected[0])

    @staticmethod
    def _doc_ai_attempted(row: dict[str, object]) -> bool:
        route = str(row.get("tailoring_route") or "")
        if route in {"openai", "fallback"}:
            return True
        if row.get("tailoring_provider") or row.get("tailoring_model") or row.get("tailoring_fallback_reason"):
            return True
        return int(row.get("tailoring_retry_count") or 0) > 0

    @staticmethod
    def _hr_email_status(row: dict[str, object]) -> str:
        return "present" if str(row.get("hiring_manager_email") or "").strip() else "not present"

    @staticmethod
    def _email_apply_assessment_for_row(row: dict[str, object]):
        if str(row.get("apply_method") or "") != "email" and not str(row.get("hiring_manager_email") or "").strip():
            return EmailApplyAssessment(False, "", "not present", "No validated HR/application email was found in the posting.")
        return assess_email_apply(
            str(row.get("description_full") or ""),
            str(row.get("apply_url") or ""),
            existing_email=str(row.get("hiring_manager_email") or ""),
        )

    @staticmethod
    def _doc_section_status(value: str) -> str:
        mapping = {"accepted": "Yes", "partial": "Partial", "local": "No"}
        return mapping.get(value.strip().lower(), "N/A")

    def _cover_letter_quality_lines(self, row: dict[str, object]) -> list[str]:
        import re
        cl_path = str(row.get("cover_letter_pdf_path") or row.get("cover_letter_docx_path") or row.get("cover_letter_path") or "")
        if not cl_path or not Path(cl_path).exists():
            return ["Cover letter not generated yet — run Generate first."]
        try:
            text = Path(cl_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ["Could not read cover letter file."]
        employer = str(row.get("employer") or "").strip().lower()
        has_company = bool(employer and employer in text.lower())
        has_metric = bool(re.search(r'\d+\s*[\%\+x]|\$\s*\d+|\d+\s*(year|month|team|person|customer|user)', text, re.IGNORECASE))
        word_count = len(text.split())
        return [
            f"Company name present:  {'Yes' if has_company else 'No — add employer name'}",
            f"Metric/number present: {'Yes' if has_metric else 'No — add a quantified result'}",
            f"Word count:            {word_count} ({'OK' if word_count <= 300 else 'Over 300 — consider trimming'})",
        ]

    def _outcome_line(self, job_id: str) -> str:
        outcome = self.database.get_latest_outcome(job_id)
        if outcome:
            return f"Recorded: {outcome}  (use dropdown above to update)"
        return "Not recorded yet — use the outcome dropdown to record what happened."

    def _open_apply_link(self) -> None:
        row = self._selected_row()
        if row and row["apply_url"]:
            webbrowser.open(row["apply_url"])

    def _open_resume(self) -> None:
        row = self._selected_row()
        if not row:
            return
        preferred_paths = [row.get("resume_docx_path", ""), row.get("resume_pdf_path", "")]
        resume_path = next((candidate for candidate in preferred_paths if candidate and Path(candidate).exists()), "")
        if not resume_path and not any(preferred_paths):
            messagebox.showwarning("Job Bot", "No generated resume is available for this row yet. Click Generate first.")
            return
        if not resume_path or not Path(resume_path).exists():
            messagebox.showwarning("Job Bot", "The generated resume file is missing on disk. Click Generate to recreate it.")
            return
        os.startfile(resume_path)

    def _open_cover_letter(self) -> None:
        row = self._selected_row()
        if not row:
            return
        cover_letter_path = row.get("cover_letter_pdf_path") or row.get("cover_letter_docx_path") or row.get("cover_letter_path")
        if not cover_letter_path:
            messagebox.showwarning("Job Bot", "No generated cover letter is available for this row yet. Click Generate first.")
            return
        if not Path(cover_letter_path).exists():
            messagebox.showwarning("Job Bot", "The generated cover letter file is missing on disk. Click Generate to recreate it.")
            return
        os.startfile(cover_letter_path)

    def _generate_documents_for_selected(self) -> None:
        if self._review_action_in_progress:
            self.status_var.set("A review queue action is already in progress.")
            return
        row = self._selected_row()
        if not row:
            return
        LOGGER.info("Review queue generation requested for %s", row["id"])
        self._set_review_action_state(
            True,
            mode="generate",
            job_id=str(row["id"]),
            status="Starting document generation...",
            context=f"{row['title']} at {row['employer']}",
            progress=0,
        )
        self.status_var.set("Generating documents...")
        self._start_review_action_polling()
        thread = threading.Thread(target=self._generate_documents_background, args=(row["id"],), daemon=True)
        thread.start()

    def _generate_documents_background(self, job_id: str) -> None:
        try:
            self.pipeline.generate_documents_for_job(job_id, progress_callback=lambda stage, message, progress: self._report_generate_progress(job_id, stage, message, progress))
            row = self.database.get_review_row(job_id)
            generated_at = self._format_generated_at(str(row.get("generated_at") or "")) if row else ""
            status = f"Documents generated{f' at {generated_at}' if generated_at else '.'}"
            self._review_action_event_queue.put(("completed", status, 8, job_id, "generate"))
        except Exception as exc:
            LOGGER.exception("Review queue generation failed for %s", job_id)
            status = f"Document generation failed: {exc}"
            self._review_action_event_queue.put(("failed", status, 0, job_id, "generate"))

    def _report_generate_progress(self, job_id: str, stage: str, message: str, progress: int) -> None:
        self._review_action_event_queue.put((stage, message, progress, job_id, "generate"))

    def _report_approval_progress(self, job_id: str, stage: str, message: str, progress: int) -> None:
        self._review_action_event_queue.put((stage, message, progress, job_id, "approve"))

    def _apply_review_action_progress(self, job_id: str, stage: str, message: str, progress: int, mode: str | None) -> None:
        if str(self._review_action_job_id or "") != str(job_id or ""):
            return
        if self._review_action_mode and mode and self._review_action_mode != mode:
            return
        self.generate_progress_var.set(progress)
        self.generate_status_var.set(message)

    def _start_review_action_polling(self) -> None:
        self._stop_review_action_polling()
        self._drain_review_action_events()

    def _stop_review_action_polling(self) -> None:
        if self._review_action_poll_after_id:
            self.root.after_cancel(self._review_action_poll_after_id)
            self._review_action_poll_after_id = None

    def _drain_review_action_events(self) -> None:
        keep_polling = self._review_action_in_progress
        while True:
            try:
                stage, message, progress, job_id, mode = self._review_action_event_queue.get_nowait()
            except queue.Empty:
                break
            if stage in {"completed", "failed"}:
                if mode == "portal_test":
                    self.portal_readiness_var.set(getattr(self.pipeline, "portal_readiness", PortalAutofillReadiness(False, "Portal autofill: unavailable", "unknown", "")).summary)
                self._set_review_action_state(False, mode=mode, job_id=job_id, status=message, context=self.generate_context_var.get(), progress=progress)
                self.status_var.set(message)
                self.refresh_view()
                keep_polling = False
            else:
                self._apply_review_action_progress(str(job_id), stage, message, progress, mode)
        if keep_polling:
            self._review_action_poll_after_id = self.root.after(100, self._drain_review_action_events)
        else:
            self._review_action_poll_after_id = None

    def _set_review_action_state(self, in_progress: bool, *, mode: str | None, job_id: str | None, status: str, context: str, progress: float) -> None:
        self._review_action_in_progress = in_progress
        self._generate_in_progress = in_progress
        self._review_action_job_id = job_id if in_progress else None
        self._review_action_mode = mode if in_progress else None
        self.generate_status_var.set(status)
        self.generate_context_var.set(context if context else "No review queue action in progress.")
        self.generate_progress_var.set(progress)
        if self.generate_button:
            self.generate_button.configure(state="disabled" if in_progress else "normal")
        if self.approve_button:
            self.approve_button.configure(state="disabled" if in_progress else "normal")
        for button in self.portal_test_buttons:
            button.configure(state="disabled" if in_progress else "normal")

    def _approve_and_send(self) -> None:
        if self._review_action_in_progress:
            self.status_var.set("A review queue action is already in progress.")
            return
        row = self._selected_row()
        if not row:
            return
        if not self._confirm_approve_and_send(row):
            self.status_var.set("Approve and Send canceled.")
            return
        self._set_review_action_state(
            True,
            mode="approve",
            job_id=str(row["id"]),
            status="Starting approved application flow...",
            context=f"{row['title']} at {row['employer']}",
            progress=0,
        )
        self.status_var.set("Starting approved application flow...")
        self._start_review_action_polling()
        thread = threading.Thread(target=self._approve_and_send_background, args=(row["id"],), daemon=True)
        thread.start()

    def _test_portal_autofill_runtime(self) -> None:
        if self._review_action_in_progress:
            self.status_var.set("A review queue action is already in progress.")
            return
        self._set_review_action_state(
            True,
            mode="portal_test",
            job_id=self.PORTAL_TEST_ACTION_ID,
            status="Testing portal autofill runtime...",
            context="Portal autofill runtime verification",
            progress=0,
        )
        self.status_var.set("Testing portal autofill runtime...")
        self._start_review_action_polling()
        thread = threading.Thread(target=self._test_portal_autofill_runtime_background, daemon=True)
        thread.start()

    def _approve_and_send_background(self, job_id: str) -> None:
        try:
            result = self.pipeline.approve_and_send(
                job_id,
                progress_callback=lambda stage, message, progress: self._report_approval_progress(job_id, stage, message, progress),
            )
            status = f"{result.status} via {result.method}"
            if result.error_message:
                status = f"{status} - {result.error_message}"
        except Exception as exc:
            status = f"send_failed - {exc}"
        self._review_action_event_queue.put(("completed" if not status.startswith("send_failed") else "failed", status, 8 if not status.startswith("send_failed") else 0, job_id, "approve"))
        self.root.after(0, self._drain_review_action_events)

    def _test_portal_autofill_runtime_background(self) -> None:
        try:
            readiness = self.pipeline.verify_portal_autofill_runtime(
                progress_callback=lambda stage, message, progress: self._review_action_event_queue.put(
                    (stage, message, progress, self.PORTAL_TEST_ACTION_ID, "portal_test")
                )
            )
            status = readiness.summary if readiness.ready else f"{readiness.summary} - {readiness.technical_detail or readiness.reason_code}"
            event = ("completed", status, 8, self.PORTAL_TEST_ACTION_ID, "portal_test")
        except Exception as exc:
            status = f"Portal runtime test failed: {exc}"
            event = ("failed", status, 0, self.PORTAL_TEST_ACTION_ID, "portal_test")
        self._review_action_event_queue.put(event)
        self.root.after(0, self._drain_review_action_events)

    def _add_tooltip(self, widget: tk.Widget, text: str) -> None:
        self._tooltips.append(Tooltip(widget, text))

    @staticmethod
    def _parse_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    def _refresh_portal_readiness(self) -> None:
        readiness_fn = getattr(self.pipeline, "portal_autofill_readiness", None)
        if callable(readiness_fn):
            readiness = readiness_fn()
            self.portal_readiness_var.set(readiness.summary)

    def _refresh_gmail_readiness(self) -> None:
        readiness_fn = getattr(getattr(self.pipeline, "gmail_client", None), "readiness_status", None)
        if callable(readiness_fn):
            _ready, summary = readiness_fn()
            self.gmail_readiness_var.set(summary)

    def _portal_readiness_for_row(self, row: dict[str, object]) -> str:
        if str(row.get("apply_method") or "") == "email":
            return "Not needed for email apply"
        return self.portal_readiness_var.get().replace("Portal autofill: ", "", 1)

    @staticmethod
    def _document_status_text(path_value: str) -> str:
        if not path_value:
            return "Not generated"
        if not Path(path_value).exists():
            return f"Generated but missing on disk: {path_value}"
        return path_value


def launch_dashboard(paths: AppPaths) -> None:
    config = load_or_create_config(paths)
    database = Database(paths.database_file)
    database.initialize()
    root = tk.Tk()
    JobBotDashboard(root, config, paths, database)
    root.mainloop()
LOGGER = logging.getLogger(__name__)
