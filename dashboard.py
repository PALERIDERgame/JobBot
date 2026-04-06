from __future__ import annotations

import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from config import AppPaths, JobBotConfig, load_or_create_config, save_config
from database import Database
from pipeline import JobBotPipeline


class JobBotDashboard:
    def __init__(self, root: tk.Tk, config: JobBotConfig, paths: AppPaths, database: Database) -> None:
        self.root = root
        self.config = config
        self.paths = paths
        self.database = database
        self.pipeline = JobBotPipeline(config, paths, database)
        self.status_var = tk.StringVar(value="Ready")

        self.resume_var = tk.StringVar(value=config.resume_source_path)
        self.threshold_var = tk.StringVar(value=str(config.scoring_threshold))
        self.keyword_var = tk.StringVar(value=config.source.keyword)
        self.location_var = tk.StringVar(value=config.source.location)
        self.gmail_enabled_var = tk.BooleanVar(value=config.gmail.enabled)
        self.recipient_var = tk.StringVar(value=config.gmail.recipient_email)
        self.sender_var = tk.StringVar(value=config.gmail.sender_email)
        self.client_secret_var = tk.StringVar(value=config.gmail.client_secrets_file)
        self.api_key_var = tk.StringVar(value=config.anthropic_api_key)

        self.review_tree: ttk.Treeview | None = None
        self.log_text: tk.Text | None = None
        self.last_run_label: ttk.Label | None = None
        self._build_ui()
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
        frame.columnconfigure(1, weight=1)
        labels = [
            ("Resume source", self.resume_var),
            ("Anthropic API key", self.api_key_var),
            ("Job keyword", self.keyword_var),
            ("Location", self.location_var),
            ("Score threshold", self.threshold_var),
            ("Gmail recipient", self.recipient_var),
            ("Gmail sender", self.sender_var),
            ("Client secrets path", self.client_secret_var),
        ]
        for idx, (label, var) in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=6, padx=(0, 10))
            show = "*" if "key" in label.lower() else ""
            ttk.Entry(frame, textvariable=var, width=70, show=show).grid(row=idx, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(frame, text="Enable Gmail delivery", variable=self.gmail_enabled_var).grid(
            row=len(labels), column=1, sticky="w", pady=6
        )

        button_row = ttk.Frame(frame)
        button_row.grid(row=len(labels) + 1, column=1, sticky="w", pady=12)
        ttk.Button(button_row, text="Browse Resume", command=self._browse_resume).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Save Config", command=self._save_config).pack(side="left")

    def _build_run_tab(self, frame: ttk.Frame) -> None:
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Button(top, text="Run Now", command=self._run_now).pack(side="left")
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=12)
        self.last_run_label = ttk.Label(top, text="No runs yet")
        self.last_run_label.pack(side="left", padx=12)

        self.log_text = tk.Text(frame, height=30, wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=(12, 0))

    def _build_review_tab(self, frame: ttk.Frame) -> None:
        columns = ("title", "employer", "score", "source", "document_status", "delivery_status")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=18)
        for column in columns:
            tree.heading(column, text=column.replace("_", " ").title())
            tree.column(column, width=150, anchor="w")
        tree.column("title", width=250)
        tree.column("employer", width=180)
        tree.pack(fill="both", expand=True)
        self.review_tree = tree

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh_view).pack(side="left")
        ttk.Button(buttons, text="Open Apply Link", command=self._open_apply_link).pack(side="left", padx=8)
        ttk.Button(buttons, text="Open Resume", command=self._open_resume).pack(side="left")

    def _browse_resume(self) -> None:
        path = filedialog.askopenfilename(
            title="Select resume source",
            filetypes=[("Resume files", "*.pdf *.txt"), ("All files", "*.*")],
        )
        if path:
            self.resume_var.set(path)

    def _save_config(self) -> None:
        self.config.resume_source_path = self.resume_var.get().strip()
        self.config.anthropic_api_key = self.api_key_var.get().strip()
        self.config.source.keyword = self.keyword_var.get().strip()
        self.config.source.location = self.location_var.get().strip()
        self.config.scoring_threshold = int(self.threshold_var.get().strip() or "70")
        self.config.gmail.enabled = self.gmail_enabled_var.get()
        self.config.gmail.recipient_email = self.recipient_var.get().strip()
        self.config.gmail.sender_email = self.sender_var.get().strip()
        self.config.gmail.client_secrets_file = self.client_secret_var.get().strip()
        save_config(self.config, self.paths.config_file)
        self.pipeline = JobBotPipeline(self.config, self.paths, self.database)
        messagebox.showinfo("Job Bot", f"Config saved to {self.paths.config_file}")

    def _run_now(self) -> None:
        self.status_var.set("Running...")
        thread = threading.Thread(target=self._run_pipeline_background, daemon=True)
        thread.start()

    def _run_pipeline_background(self) -> None:
        result = self.pipeline.run()
        self.root.after(
            0,
            lambda: (
                self.status_var.set(f"{result.status} - {result.message}"),
                self.refresh_view(),
            ),
        )

    def refresh_view(self) -> None:
        self._refresh_logs()
        self._refresh_runs()
        self._refresh_review_queue()

    def _refresh_logs(self) -> None:
        if not self.log_text:
            return
        content = ""
        if self.paths.log_file.exists():
            content = self.paths.log_file.read_text(encoding="utf-8", errors="ignore")[-8000:]
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", content or "No logs yet.")

    def _refresh_runs(self) -> None:
        run = self.database.latest_run()
        if self.last_run_label:
            if not run:
                self.last_run_label.config(text="No runs yet")
            else:
                self.last_run_label.config(
                    text=f"Last run: {run['status']} | stage={run['stage']} | seen={run['jobs_seen']} matched={run['jobs_matched']}"
                )

    def _refresh_review_queue(self) -> None:
        if not self.review_tree:
            return
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        for row in self.database.list_review_rows():
            self.review_tree.insert(
                "",
                "end",
                iid=row["id"],
                values=(
                    row["title"],
                    row["employer"],
                    row["score"],
                    row["source"],
                    row["document_status"],
                    row["delivery_status"],
                ),
            )

    def _selected_row(self):
        if not self.review_tree:
            return None
        selected = self.review_tree.selection()
        if not selected:
            messagebox.showwarning("Job Bot", "Select a review item first.")
            return None
        job_id = selected[0]
        for row in self.database.list_review_rows():
            if row["id"] == job_id:
                return row
        return None

    def _open_apply_link(self) -> None:
        row = self._selected_row()
        if row and row["apply_url"]:
            webbrowser.open(row["apply_url"])

    def _open_resume(self) -> None:
        row = self._selected_row()
        if not row:
            return
        resume_path = row["resume_pdf_path"]
        if not resume_path:
            messagebox.showwarning("Job Bot", "No generated resume available for this row.")
            return
        os.startfile(resume_path)


def launch_dashboard(paths: AppPaths) -> None:
    config = load_or_create_config(paths)
    database = Database(paths.database_file)
    database.initialize()
    root = tk.Tk()
    JobBotDashboard(root, config, paths, database)
    root.mainloop()
