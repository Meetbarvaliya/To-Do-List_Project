import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import json
import re
from datetime import datetime, timedelta
import requests
import os
from typing import Optional, List, Dict

# --------------------------
# Configuration
# --------------------------
# You provided this key. It's placed here for convenience.
# Optionally set environment variable QUOTE_API_KEY to override.
QUOTE_API_KEY = os.getenv("QUOTE_API_KEY", "n164ne0xMn4RZpOjHwW0yA==psvs8DQsSZ7PGVrB")
# Default API endpoint (API-Ninjas style). If your key is for a different service,
# change QUOTE_API_URL accordingly.
QUOTE_API_URL = "https://api.api-ninjas.com/v1/quotes?category=motivational"

TASKS_FILE = "tasks.json"

# --------------------------
# Domain classes
# --------------------------
class Task:
    def __init__(self, title: str, due: Optional[str] = None, priority: str = "medium", status: str = "pending"):
        self.title = title.strip()
        self.due = due  # ISO format string or None
        self.priority = priority.lower()
        self.status = status.lower()

    def to_dict(self) -> Dict:
        return {"title": self.title, "due": self.due, "priority": self.priority, "status": self.status}

    @staticmethod
    def from_dict(d: Dict):
        return Task(d.get("title", ""), d.get("due"), d.get("priority", "medium"), d.get("status", "pending"))

    def display_due(self):
        return self.due if self.due else "-"

class TaskManager:
    def __init__(self):
        self.tasks: List[Task] = []

    def add(self, task: Task):
        self.tasks.append(task)

    def delete(self, index: int):
        if 0 <= index < len(self.tasks):
            del self.tasks[index]

    def update(self, index: int, task: Task):
        if 0 <= index < len(self.tasks):
            self.tasks[index] = task

    def save(self, filename: str = TASKS_FILE):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump([t.to_dict() for t in self.tasks], f, indent=2)
        except Exception as e:
            raise IOError(f"Failed to save tasks: {e}")

    def load(self, filename: str = TASKS_FILE):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.tasks = [Task.from_dict(d) for d in data]
        except FileNotFoundError:
            self.tasks = []  # no file yet
        except Exception as e:
            raise IOError(f"Failed to load tasks: {e}")

# --------------------------
# Natural language parsing
# --------------------------
def parse_nl_input(text: str) -> Task:
    
    original = text.strip()
    lowered = original.lower()

    # Default values
    due_dt = None
    priority = "medium"

    # Priority
    p_match = re.search(r"\b(high|medium|low)\s*priority\b", lowered)
    if not p_match:
        p_match = re.search(r"\bpriority\s*[:\-]?\s*(high|medium|low)\b", lowered)
    if p_match:
        priority = p_match.group(1)
        # remove that portion from title
        original = re.sub(re.escape(p_match.group(0)), "", original, flags=re.I).strip()

    # Date: dd/mm/yyyy or d/m/yyyy
    date_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", lowered)
    if date_match:
        date_str = date_match.group(1)
        try:
            dt = datetime.strptime(date_str, "%d/%m/%Y")
            due_dt = dt
            original = re.sub(re.escape(date_str), "", original, flags=re.I).strip()
        except:
            pass

    # Date: yyyy-mm-dd
    date_match2 = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", lowered)
    if date_match2 and due_dt is None:
        date_str = date_match2.group(1)
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            due_dt = dt
            original = re.sub(re.escape(date_str), "", original, flags=re.I).strip()
        except:
            pass

    # today / tomorrow
    if due_dt is None:
        if re.search(r"\btoday\b", lowered):
            due_dt = datetime.now()
            original = re.sub(r"\btoday\b", "", original, flags=re.I).strip()
        elif re.search(r"\btomorrow\b", lowered):
            due_dt = datetime.now() + timedelta(days=1)
            original = re.sub(r"\btomorrow\b", "", original, flags=re.I).strip()

    # Time extraction (e.g., 5pm, 5:30 pm, 17:30)
    time_match = re.search(r"\b(\d{1,2}(:\d{2})?\s*(am|pm)?)\b", lowered)
    if time_match:
        time_text = time_match.group(1)
        # Try parse time
        try:
            t = None
            if re.search(r"(am|pm)$", time_text.strip()):
                t = datetime.strptime(time_text.strip(), "%I:%M %p") if ":" in time_text else datetime.strptime(time_text.strip(), "%I %p")
            else:
                # 24-hour or H:MM
                t = datetime.strptime(time_text.strip(), "%H:%M") if ":" in time_text else datetime.strptime(time_text.strip(), "%H")
            # combine date and time
            if due_dt is None:
                due_dt = datetime.now()
            due_dt = due_dt.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            original = re.sub(re.escape(time_text), "", original, flags=re.I).strip()
        except:
            # ignore time parse failure
            pass

    # Clean title: remove connector words like "by", "on", "at", trailing punctuation
    title = original
    title = re.sub(r"\bby\b|\bon\b|\bat\b", "", title, flags=re.I).strip()
    title = title.strip(" ,.-;:")

    # If title empty, fall back to the original lowered input
    if not title:
        title = lowered if lowered else "Untitled task"

    due_iso = due_dt.strftime("%Y-%m-%d %H:%M") if due_dt else None

    return Task(title=title, due=due_iso, priority=priority, status="pending")

# --------------------------
# Quotes API integration with fallback
# --------------------------
LOCAL_FALLBACK_QUOTES = [
    "Start where you are. Use what you have. Do what you can. — Arthur Ashe",
    "The secret of getting ahead is getting started. — Mark Twain",
    "Don't watch the clock; do what it does. Keep going. — Sam Levenson",
    "Success usually comes to those who are too busy to be looking for it. — Henry David Thoreau",
]

def fetch_quote(api_key: str = QUOTE_API_KEY) -> str:
    headers = {"X-Api-Key": api_key}
    try:
        resp = requests.get(QUOTE_API_URL, headers=headers, timeout=6)
        if resp.status_code == 200:
            # API-Ninjas returns a list of quotes
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                q = data[0].get("quote", "") or f"{data[0].get('title', '')} {data[0].get('author', '')}"
                author = data[0].get("author", "")
                if author:
                    return f"{q} — {author}" if "—" not in q else q
                return q
            # Sometimes API returns dict with 'quote' etc.
            if isinstance(data, dict) and "quote" in data:
                q = data.get("quote", "")
                a = data.get("author", "")
                return f"{q} — {a}" if a else q
        # Non-200 or unexpected format -> fallback
    except Exception:
        pass

    # fallback random local quote
    import random
    return random.choice(LOCAL_FALLBACK_QUOTES)

# --------------------------
# GUI Application
# --------------------------
class ToDoApp:
    def __init__(self, root):
        self.root = root
        root.title("Smart To-Do List (Student Project)")
        root.geometry("820x520")
        self.manager = TaskManager()
        try:
            self.manager.load()
        except Exception as e:
            messagebox.showwarning("Load error", f"Could not load tasks automatically: {e}")

        self.setup_styles()
        self.create_widgets()
        self.refresh_task_view()

    def setup_styles(self):
        style = ttk.Style(self.root)
        # Use a theme that looks modern if available
        try:
            style.theme_use("clam")
        except:
            pass
        style.configure("TButton", padding=6, relief="flat", font=("Segoe UI", 10))
        style.configure("TEntry", padding=6, font=("Segoe UI", 10))
        style.configure("Treeview", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))

    def create_widgets(self):
        # Top frame: input and quote
        top = ttk.Frame(self.root, padding=(10,10))
        top.pack(side="top", fill="x")

        ttk.Label(top, text="Add task (natural language):", style="Header.TLabel").pack(anchor="w")
        in_frame = ttk.Frame(top)
        in_frame.pack(fill="x", pady=(6,8))

        self.input_var = tk.StringVar()
        self.entry = ttk.Entry(in_frame, textvariable=self.input_var)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.on_add_task())

        add_btn = ttk.Button(in_frame, text="Add Task", command=self.on_add_task)
        add_btn.pack(side="left", padx=6)

        quote_btn = ttk.Button(in_frame, text="Get Motivational Quote", command=self.on_get_quote)
        quote_btn.pack(side="left", padx=6)

        self.quote_var = tk.StringVar(value="Welcome! Add a task or press 'Get Motivational Quote'.")
        quote_lbl = ttk.Label(top, textvariable=self.quote_var, wraplength=760)
        quote_lbl.pack(anchor="w", pady=(4,4))

        # Middle: Treeview with tasks
        mid = ttk.Frame(self.root, padding=(10,6))
        mid.pack(fill="both", expand=True)

        columns = ("Title", "Due", "Priority", "Status")
        self.tree = ttk.Treeview(mid, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=180 if col=="Title" else 120, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.on_edit_task())

        scrollbar = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Bottom: controls
        bot = ttk.Frame(self.root, padding=(10,10))
        bot.pack(fill="x")

        btn_frame = ttk.Frame(bot)
        btn_frame.pack(side="left")

        del_btn = ttk.Button(btn_frame, text="Delete Task", command=self.on_delete_task)
        del_btn.grid(row=0, column=0, padx=4, pady=4)

        edit_btn = ttk.Button(btn_frame, text="Edit Task", command=self.on_edit_task)
        edit_btn.grid(row=0, column=1, padx=4, pady=4)

        done_btn = ttk.Button(btn_frame, text="Mark Done", command=self.on_mark_done)
        done_btn.grid(row=0, column=2, padx=4, pady=4)

        save_btn = ttk.Button(btn_frame, text="Save Tasks", command=self.on_save)
        save_btn.grid(row=0, column=3, padx=4, pady=4)

        load_btn = ttk.Button(btn_frame, text="Load Tasks", command=self.on_load)
        load_btn.grid(row=0, column=4, padx=4, pady=4)

        filter_frame = ttk.Frame(bot)
        filter_frame.pack(side="right")

        ttk.Label(filter_frame, text="Filter:").grid(row=0, column=0, padx=6)
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var, width=24)
        self.filter_entry.grid(row=0, column=1)
        fbtn = ttk.Button(filter_frame, text="Apply", command=self.on_filter)
        fbtn.grid(row=0, column=2, padx=4)
        rbtn = ttk.Button(filter_frame, text="Reset", command=self.on_reset_filter)
        rbtn.grid(row=0, column=3, padx=4)

    def refresh_task_view(self, filtered: Optional[List[int]] = None):
        # Clear
        for r in self.tree.get_children():
            self.tree.delete(r)
        # Populate
        for idx, task in enumerate(self.manager.tasks):
            if filtered is not None and idx not in filtered:
                continue
            due_text = task.display_due()
            self.tree.insert("", "end", iid=str(idx), values=(task.title, due_text, task.priority.title(), task.status.title()))

    def on_add_task(self):
        text = self.input_var.get().strip()
        if not text:
            messagebox.showerror("Input error", "Please type a task description in natural language.")
            return
        try:
            task = parse_nl_input(text)
            self.manager.add(task)
            self.input_var.set("")
            self.refresh_task_view()
        except Exception as e:
            messagebox.showerror("Parsing error", f"Could not parse the input: {e}")

    def on_delete_task(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select task", "Please select a task to delete.")
            return
        idx = int(sel[0])
        confirm = messagebox.askyesno("Delete", f"Delete task: {self.manager.tasks[idx].title}?")
        if confirm:
            self.manager.delete(idx)
            self.refresh_task_view()

    def on_edit_task(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select task", "Please select a task to edit (double-click or select and press Edit).")
            return
        idx = int(sel[0])
        old = self.manager.tasks[idx]
        
        new_title = simpledialog.askstring("Edit title", "Task title:", initialvalue=old.title, parent=self.root)
        if new_title is None:
            return  
        new_due = simpledialog.askstring("Edit due", "Due (YYYY-MM-DD HH:MM) or blank:", initialvalue=(old.due or ""), parent=self.root)
        new_priority = simpledialog.askstring("Edit priority", "Priority (high/medium/low):", initialvalue=old.priority, parent=self.root)
        new_status = simpledialog.askstring("Edit status", "Status (pending/done):", initialvalue=old.status, parent=self.root)
        try:
            if new_due and new_due.strip():
                
                _ = datetime.strptime(new_due.strip(), "%Y-%m-%d %H:%M")
                due_val = new_due.strip()
            elif new_due and new_due.strip() == "":
                due_val = None
            else:
                due_val = old.due
        except:
            messagebox.showwarning("Invalid due", "Invalid due format. Keep previous value.")
            due_val = old.due
        priority_val = new_priority.lower() if new_priority and new_priority.lower() in ("high", "medium", "low") else old.priority
        status_val = new_status.lower() if new_status and new_status.lower() in ("pending", "done") else old.status
        updated = Task(new_title, due_val, priority_val, status_val)
        self.manager.update(idx, updated)
        self.refresh_task_view()

    def on_mark_done(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select task", "Please select a task to mark done.")
            return
        idx = int(sel[0])
        t = self.manager.tasks[idx]
        t.status = "done"
        self.manager.update(idx, t)
        self.refresh_task_view()

    def on_save(self):
        try:
            self.manager.save()
            messagebox.showinfo("Saved", f"Tasks saved to {TASKS_FILE}")
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    def on_load(self):
        # allow user to choose file
        filename = filedialog.askopenfilename(title="Load tasks JSON", filetypes=[("JSON files","*.json"),("All files","*.*")])
        if not filename:
            return
        try:
            self.manager.load(filename)
            messagebox.showinfo("Loaded", f"Loaded tasks from {filename}")
            self.refresh_task_view()
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def on_get_quote(self):
        self.quote_var.set("Fetching quote...")
        self.root.update_idletasks()
        try:
            q = fetch_quote()
            self.quote_var.set(q)
        except Exception as e:
            self.quote_var.set("Could not fetch quote. Try again later.")
            messagebox.showwarning("Quote error", str(e))

    def on_filter(self):
        term = self.filter_var.get().strip().lower()
        if not term:
            self.refresh_task_view()
            return
        filtered = []
        for i, t in enumerate(self.manager.tasks):
            if term in t.title.lower() or (t.due and term in t.due.lower()) or term in t.priority.lower() or term in t.status.lower():
                filtered.append(i)
        self.refresh_task_view(filtered=filtered)

    def on_reset_filter(self):
        self.filter_var.set("")
        self.refresh_task_view()

# --------------------------
# Run
# --------------------------
def main():
    root = tk.Tk()
    app = ToDoApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
