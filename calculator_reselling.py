"""Десктопное приложение «Калькулятор перекупства»."""

import customtkinter as ctk
from tkinter import Menu, TclError, messagebox, ttk
import json
import os
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from datetime import datetime


class App(ctk.CTk):
    """Главное окно калькулятора."""

    HISTORY_LIMIT = 5
    ACCENT = "#1f538d"
    ACCENT_HOVER = "#173f6b"
    BG = "#111827"
    CARD = "#1f2937"
    TEXT = "#f3f4f6"
    MUTED = "#aeb8c7"
    ERROR = "#d64545"

    FIELDS = (
        ("purchase", "💰  Цена покупки (₽)", ""),
        ("sale", "🏷  Цена продажи (₽)", ""),
        ("repair", "🛠  Расходы на ремонт (₽)", "0"),
        ("commission", "📊  Комиссия (%)", "0"),
        ("extra", "➕  Дополнительные расходы (₽)", "0"),
    )

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Калькулятор перекупства")
        self.geometry("1060x760")
        self.minsize(900, 680)
        self.configure(fg_color=self.BG)

        # История хранится рядом с программой.
        self.history_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "calculation_history.json"
        )
        self.entries = {}
        self.result_vars = {
            "expenses": ctk.StringVar(value="—"),
            "profit": ctk.StringVar(value="—"),
            "margin": ctk.StringVar(value="—"),
            "roi": ctk.StringVar(value="—"),
        }
        self.history = self._load_history()

        self._configure_styles()
        self._build_interface()
        self._refresh_history_table()
        self._restore_last_result()

    def _configure_styles(self):
        """Настраивает внешний вид стандартной таблицы ttk."""
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "History.Treeview",
            background=self.CARD,
            fieldbackground=self.CARD,
            foreground=self.TEXT,
            rowheight=30,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "History.Treeview.Heading",
            background="#374151",
            foreground=self.TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map("History.Treeview", background=[("selected", self.ACCENT)])

    def _shadow_card(self, parent, row, column, **grid_options):
        """Создаёт карточку с простой имитацией мягкой тени."""
        wrapper = ctk.CTkFrame(parent, fg_color="#080d16", corner_radius=14)
        wrapper.grid(row=row, column=column, **grid_options)
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)
        card = ctk.CTkFrame(wrapper, fg_color=self.CARD, corner_radius=12)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 3), pady=(0, 3))
        return card

    def _build_interface(self):
        """Собирает все элементы главного окна."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(24, 14))
        header.grid_columnconfigure(0, weight=1)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_box,
            text="Калькулятор перекупства",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="Оцените прибыльность сделки и следите за ценами маркетплейса",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).pack(anchor="w", pady=(3, 0))
        ctk.CTkButton(
            header,
            text="📊  Мониторинг цен",
            width=180,
            height=40,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.open_price_monitor,
        ).grid(row=0, column=1, sticky="e", padx=(20, 0))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 20))
        content.grid_columnconfigure(0, weight=5, uniform="main")
        content.grid_columnconfigure(1, weight=4, uniform="main")
        content.grid_rowconfigure(0, weight=1)

        input_card = self._shadow_card(
            content, 0, 0, sticky="nsew", padx=(0, 10), pady=(0, 12)
        )
        result_card = self._shadow_card(
            content, 0, 1, sticky="nsew", padx=(10, 0), pady=(0, 12)
        )
        self._build_input_card(input_card)
        self._build_result_card(result_card)

        history_card = self._shadow_card(
            self, 2, 0, sticky="ew", padx=30, pady=(0, 28)
        )
        self._build_history_card(history_card)

    def _build_input_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            card,
            text="Параметры сделки",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))

        # Прокручиваемая область сохраняет доступ ко всем полям в низком окне.
        fields_frame = ctk.CTkScrollableFrame(
            card,
            fg_color="transparent",
            scrollbar_button_color="#4b5563",
            scrollbar_button_hover_color=self.ACCENT,
        )
        fields_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 5), pady=(0, 10))
        fields_frame.grid_columnconfigure(0, weight=1)

        for row, (key, label, default) in enumerate(self.FIELDS, start=1):
            ctk.CTkLabel(
                fields_frame, text=label, text_color=self.TEXT, font=("Segoe UI", 12)
            ).grid(row=row * 2 - 1, column=0, sticky="w", padx=16, pady=(5, 2))
            entry = ctk.CTkEntry(
                fields_frame,
                height=35,
                fg_color="#111827",
                border_color="#4b5563",
                text_color=self.TEXT,
                placeholder_text="Введите значение",
            )
            entry.grid(row=row * 2, column=0, sticky="ew", padx=16, pady=(0, 5))
            if default:
                entry.insert(0, default)
            entry.bind("<Return>", lambda _event: self.calculate())
            entry.bind("<KeyRelease>", lambda _event, item=entry: self._reset_entry(item))
            self.entries[key] = entry

        ctk.CTkButton(
            fields_frame,
            text="Рассчитать",
            height=43,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self.calculate,
        ).grid(row=12, column=0, sticky="ew", padx=16, pady=(17, 16))

    def _build_result_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text="Результаты",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 14))

        items = (
            ("expenses", "Общие расходы", "💳"),
            ("profit", "Чистая прибыль", "💰"),
            ("margin", "Маржинальность", "📈"),
            ("roi", "ROI", "🎯"),
        )
        for row, (key, label, icon) in enumerate(items, start=1):
            box = ctk.CTkFrame(card, fg_color="#111827", corner_radius=10)
            box.grid(row=row, column=0, sticky="ew", padx=24, pady=7)
            box.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                box, text=f"{icon}  {label}", text_color=self.MUTED, font=("Segoe UI", 12)
            ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))
            ctk.CTkLabel(
                box,
                textvariable=self.result_vars[key],
                text_color=self.ACCENT,
                font=ctk.CTkFont(family="Segoe UI", size=23, weight="bold"),
            ).grid(row=1, column=0, sticky="w", padx=16, pady=(1, 12))

        ctk.CTkLabel(
            card,
            text="Комиссия рассчитывается\nот цены продажи.",
            justify="left",
            text_color=self.MUTED,
            font=("Segoe UI", 11),
        ).grid(row=5, column=0, sticky="sw", padx=24, pady=(18, 20))

        ctk.CTkButton(
            card,
            text="Сбросить результат",
            height=38,
            fg_color="transparent",
            hover_color="#374151",
            border_width=1,
            border_color="#596579",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.reset_results,
        ).grid(row=6, column=0, sticky="ew", padx=24, pady=(0, 22))

    def _build_history_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 8))
        ctk.CTkLabel(
            title_row,
            text="Последние расчёты",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            title_row,
            text="Очистить историю",
            width=140,
            height=30,
            fg_color="transparent",
            hover_color="#374151",
            border_width=1,
            border_color="#596579",
            text_color=self.MUTED,
            command=self.clear_history,
        ).pack(side="right")

        columns = ("time", "purchase", "sale", "profit", "roi")
        self.history_table = ttk.Treeview(
            card, columns=columns, show="headings", height=5, style="History.Treeview"
        )
        headings = {
            "time": "Дата и время",
            "purchase": "Покупка",
            "sale": "Продажа",
            "profit": "Прибыль",
            "roi": "ROI",
        }
        widths = {"time": 145, "purchase": 145, "sale": 145, "profit": 145, "roi": 95}
        for column in columns:
            self.history_table.heading(column, text=headings[column])
            self.history_table.column(column, width=widths[column], anchor="center")
        self.history_table.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 18))

    @staticmethod
    def _parse_number(value):
        """Преобразует число, разрешая пробелы и запятую как разделитель."""
        cleaned = value.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        number = float(cleaned)
        if number < 0:
            raise ValueError
        return number

    def _reset_entry(self, entry):
        entry.configure(border_color="#4b5563")

    def reset_results(self):
        """Очищает рассчитанные показатели, не затрагивая историю."""
        for variable in self.result_vars.values():
            variable.set("—")

    def open_price_monitor(self):
        """Открывает отдельное окно мониторинга цен."""
        if hasattr(self, "monitor_window") and self.monitor_window.winfo_exists():
            self.monitor_window.focus()
            return
        self.monitor_window = PriceMonitorWindow(self)

    def calculate(self):
        """Проверяет ввод, выполняет расчёт и сохраняет результат."""
        values = {}
        invalid = []
        for key, entry in self.entries.items():
            try:
                values[key] = self._parse_number(entry.get())
                self._reset_entry(entry)
            except (ValueError, TypeError):
                entry.configure(border_color=self.ERROR, border_width=2)
                invalid.append(entry)

        if invalid:
            invalid[0].focus_set()
            messagebox.showerror(
                "Ошибка ввода",
                "Заполните выделенные поля числами, равными или больше нуля.",
                parent=self,
            )
            return

        commission_rub = values["sale"] * values["commission"] / 100
        expenses = (
            values["purchase"]
            + values["repair"]
            + values["extra"]
            + commission_rub
        )
        profit = values["sale"] - expenses
        margin = profit / values["sale"] * 100 if values["sale"] else 0
        roi = profit / expenses * 100 if expenses else 0

        self.result_vars["expenses"].set(self._format_money(expenses))
        self.result_vars["profit"].set(self._format_money(profit))
        self.result_vars["margin"].set(f"{margin:,.2f} %".replace(",", " "))
        self.result_vars["roi"].set(f"{roi:,.2f} %".replace(",", " "))

        record = {
            "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "purchase": values["purchase"],
            "sale": values["sale"],
            "expenses": expenses,
            "profit": profit,
            "margin": margin,
            "roi": roi,
        }
        self.history.insert(0, record)
        self.history = self.history[: self.HISTORY_LIMIT]
        self._save_history()
        self._refresh_history_table()

    @staticmethod
    def _format_money(value):
        """Форматирует рублёвую сумму с разделителями тысяч."""
        if value == int(value):
            return f"{value:,.0f} ₽".replace(",", " ")
        return f"{value:,.2f} ₽".replace(",", " ")

    def _load_history(self):
        try:
            with open(self.history_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data[: self.HISTORY_LIMIT] if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _save_history(self):
        try:
            with open(self.history_path, "w", encoding="utf-8") as file:
                json.dump(self.history, file, ensure_ascii=False, indent=2)
        except OSError as error:
            messagebox.showwarning(
                "История не сохранена",
                f"Не удалось записать файл истории:\n{error}",
                parent=self,
            )

    def _restore_last_result(self):
        """Восстанавливает результаты последнего расчёта после запуска."""
        if not self.history:
            return

        try:
            record = self.history[0]
            sale = float(record["sale"])
            profit = float(record["profit"])

            # Старые записи не содержат expenses и margin — вычисляем их заново.
            expenses = float(record.get("expenses", sale - profit))
            margin = float(
                record.get("margin", profit / sale * 100 if sale else 0)
            )
            roi = float(record.get("roi", profit / expenses * 100 if expenses else 0))

            self.result_vars["expenses"].set(self._format_money(expenses))
            self.result_vars["profit"].set(self._format_money(profit))
            self.result_vars["margin"].set(
                f"{margin:,.2f} %".replace(",", " ")
            )
            self.result_vars["roi"].set(f"{roi:,.2f} %".replace(",", " "))
        except (KeyError, TypeError, ValueError):
            # Повреждённая старая запись не должна мешать запуску программы.
            return

    def _refresh_history_table(self):
        for item in self.history_table.get_children():
            self.history_table.delete(item)
        for record in self.history:
            try:
                self.history_table.insert(
                    "",
                    "end",
                    values=(
                        record["time"],
                        self._format_money(float(record["purchase"])),
                        self._format_money(float(record["sale"])),
                        self._format_money(float(record["profit"])),
                        f'{float(record["roi"]):,.2f} %'.replace(",", " "),
                    ),
                )
            except (KeyError, TypeError, ValueError):
                continue

    def clear_history(self):
        """Очищает историю после подтверждения пользователя."""
        if not self.history:
            return
        if messagebox.askyesno(
            "Очистка истории", "Удалить все сохранённые расчёты?", parent=self
        ):
            self.history = []
            self._save_history()
            self._refresh_history_table()


class PriceMonitorWindow(ctk.CTkToplevel):
    """Окно получения и просмотра статистики цен маркетплейса."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.items = []
        self.cache_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "marketplace_cache.json"
        )
        self.favorites_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "marketplace_favorites.json"
        )
        self.favorites = self._load_favorites()

        self.title("Мониторинг цен маркетплейса")
        self.geometry("1120x720")
        self.minsize(880, 600)
        self.configure(fg_color=parent.BG)
        self.transient(parent)

        self.server_var = ctk.StringVar(value="Сервер: —")
        self.updated_var = ctk.StringVar(value="Обновлено: —")
        self.summary_var = ctk.StringVar(value="Предметов: —   Продано: —   Средняя цена: —")
        self.status_var = ctk.StringVar(value="Укажите адрес API и нажмите «Обновить»")
        self.only_favorites_var = ctk.BooleanVar(value=False)
        self._build_interface()
        self._load_cache()

    def _build_interface(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="Мониторинг цен",
            text_color=self.parent.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=28, pady=(22, 12))

        settings = ctk.CTkFrame(self, fg_color=self.parent.CARD, corner_radius=12)
        settings.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 14))
        settings.grid_columnconfigure(0, weight=5)
        settings.grid_columnconfigure(1, weight=3)

        ctk.CTkLabel(
            settings, text="Полный URL API", text_color=self.parent.MUTED
        ).grid(row=0, column=0, sticky="w", padx=(18, 8), pady=(14, 3))
        ctk.CTkLabel(
            settings, text="API-ключ (не сохраняется)", text_color=self.parent.MUTED
        ).grid(row=0, column=1, sticky="w", padx=8, pady=(14, 3))

        self.url_entry = ctk.CTkEntry(
            settings,
            height=38,
            placeholder_text="https://example.com/v1/ext/marketplace/items/15",
            fg_color="#111827",
            border_color="#4b5563",
        )
        self.url_entry.grid(row=1, column=0, sticky="ew", padx=(18, 8), pady=(0, 16))
        self._enable_edit_shortcuts(self.url_entry)

        self.token_entry = ctk.CTkEntry(
            settings,
            height=38,
            placeholder_text="Введите новый ключ",
            show="●",
            fg_color="#111827",
            border_color="#4b5563",
        )
        self.token_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 16))
        self._enable_edit_shortcuts(self.token_entry)

        self.auth_menu = ctk.CTkOptionMenu(
            settings,
            values=["Bearer", "X-API-Key", "Без авторизации"],
            width=150,
            height=38,
            fg_color="#374151",
            button_color=self.parent.ACCENT,
            button_hover_color=self.parent.ACCENT_HOVER,
        )
        self.auth_menu.grid(row=1, column=2, padx=8, pady=(0, 16))

        self.refresh_button = ctk.CTkButton(
            settings,
            text="Обновить",
            width=125,
            height=38,
            fg_color=self.parent.ACCENT,
            hover_color=self.parent.ACCENT_HOVER,
            command=self.refresh_data,
        )
        self.refresh_button.grid(row=1, column=3, padx=(8, 18), pady=(0, 16))

        content = ctk.CTkFrame(self, fg_color=self.parent.CARD, corner_radius=12)
        content.grid(row=2, column=0, sticky="nsew", padx=28, pady=(0, 24))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(4, weight=1)

        info = ctk.CTkFrame(content, fg_color="transparent")
        info.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        ctk.CTkLabel(
            info, textvariable=self.server_var, text_color=self.parent.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            info, textvariable=self.updated_var, text_color=self.parent.MUTED
        ).pack(side="right")

        ctk.CTkLabel(
            content, textvariable=self.summary_var, text_color=self.parent.MUTED
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 10))

        self.search_entry = ctk.CTkEntry(
            content,
            height=36,
            placeholder_text="🔎  Поиск по названию или ID предмета",
            fg_color="#111827",
            border_color="#4b5563",
        )
        self.search_entry.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        self._enable_edit_shortcuts(self.search_entry)
        self.search_entry.bind("<KeyRelease>", lambda _event: self._fill_table())

        favorites_bar = ctk.CTkFrame(content, fg_color="transparent")
        favorites_bar.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.favorite_id_entry = ctk.CTkEntry(
            favorites_bar,
            width=150,
            height=34,
            placeholder_text="ID предмета",
            fg_color="#111827",
            border_color="#4b5563",
        )
        self.favorite_id_entry.pack(side="left", padx=(0, 8))
        self._enable_edit_shortcuts(self.favorite_id_entry)
        ctk.CTkButton(
            favorites_bar,
            text="★ Добавить",
            width=115,
            height=34,
            fg_color=self.parent.ACCENT,
            hover_color=self.parent.ACCENT_HOVER,
            command=self.add_favorite,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            favorites_bar,
            text="Убрать",
            width=90,
            height=34,
            fg_color="transparent",
            hover_color="#374151",
            border_width=1,
            border_color="#596579",
            command=self.remove_favorite,
        ).pack(side="left")
        ctk.CTkSwitch(
            favorites_bar,
            text="Только избранное",
            variable=self.only_favorites_var,
            command=self._fill_table,
            progress_color=self.parent.ACCENT,
        ).pack(side="right")

        columns = ("id", "name", "count", "sold", "average", "minimum", "maximum")
        self.table = ttk.Treeview(
            content, columns=columns, show="headings", style="History.Treeview"
        )
        headings = {
            "id": "ID", "name": "Предмет", "count": "Всего",
            "sold": "Продано", "average": "Средняя цена",
            "minimum": "Минимум", "maximum": "Максимум",
        }
        widths = {
            "id": 65, "name": 250, "count": 80, "sold": 80,
            "average": 145, "minimum": 145, "maximum": 145,
        }
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(
                column, width=widths[column], anchor="w" if column == "name" else "center"
            )
        self.table.grid(row=4, column=0, sticky="nsew", padx=18, pady=(0, 8))
        self.table.bind("<Double-1>", lambda _event: self.add_favorite())

        ctk.CTkLabel(
            content, textvariable=self.status_var, text_color=self.parent.MUTED
        ).grid(row=5, column=0, sticky="w", padx=18, pady=(0, 14))

    def _enable_edit_shortcuts(self, entry):
        """Добавляет надёжную вставку и контекстное меню для CTkEntry."""
        # CTkEntry содержит внутри обычный tkinter.Entry — привязываемся к нему,
        # чтобы сочетания работали в том числе при русской раскладке Windows.
        widget = getattr(entry, "_entry", entry)

        def paste(_event=None):
            try:
                value = self.clipboard_get()
                if widget.selection_present():
                    widget.delete("sel.first", "sel.last")
                widget.insert("insert", value)
                widget.event_generate("<KeyRelease>")
            except TclError:
                pass
            return "break"

        def copy(_event=None):
            try:
                value = widget.selection_get()
                self.clipboard_clear()
                self.clipboard_append(value)
            except TclError:
                pass
            return "break"

        def cut(_event=None):
            try:
                copy()
                widget.delete("sel.first", "sel.last")
                widget.event_generate("<KeyRelease>")
            except TclError:
                pass
            return "break"

        def select_all(_event=None):
            widget.selection_range(0, "end")
            widget.icursor("end")
            return "break"

        def control_key(event):
            # keycode не зависит от выбранной раскладки клавиатуры.
            actions = {65: select_all, 67: copy, 86: paste, 88: cut}
            action = actions.get(event.keycode)
            return action(event) if action else None

        menu = Menu(self, tearoff=False)
        menu.add_command(label="Вырезать", command=cut)
        menu.add_command(label="Копировать", command=copy)
        menu.add_command(label="Вставить", command=paste)
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=select_all)

        def show_menu(event):
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Control-KeyPress>", control_key, add="+")
        widget.bind("<Shift-Insert>", paste, add="+")
        widget.bind("<Button-3>", show_menu, add="+")

    def _load_favorites(self):
        """Загружает сохранённые ID избранных предметов."""
        try:
            with open(self.favorites_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return {str(item_id).strip() for item_id in data if str(item_id).strip()}
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
            return set()

    def _save_favorites(self):
        try:
            with open(self.favorites_path, "w", encoding="utf-8") as file:
                json.dump(sorted(self.favorites), file, ensure_ascii=False, indent=2)
        except OSError as error:
            messagebox.showwarning(
                "Избранное не сохранено",
                f"Не удалось сохранить список избранного:\n{error}",
                parent=self,
            )

    def _selected_or_entered_id(self):
        """Возвращает введённый ID либо ID выбранной строки таблицы."""
        entered = self.favorite_id_entry.get().strip()
        if entered:
            return entered
        selection = self.table.selection()
        if selection:
            values = self.table.item(selection[0], "values")
            if values:
                return str(values[0]).strip()
        return ""

    def add_favorite(self):
        item_id = self._selected_or_entered_id()
        if not item_id:
            messagebox.showinfo(
                "Добавление в избранное",
                "Введите ID предмета или выберите строку в таблице.",
                parent=self,
            )
            return
        self.favorites.add(item_id)
        self._save_favorites()
        self.favorite_id_entry.delete(0, "end")
        self._fill_table()
        self.status_var.set(f"Предмет ID {item_id} добавлен в избранное")

    def remove_favorite(self):
        item_id = self._selected_or_entered_id()
        if not item_id:
            messagebox.showinfo(
                "Удаление из избранного",
                "Введите ID предмета или выберите строку в таблице.",
                parent=self,
            )
            return
        self.favorites.discard(item_id)
        self._save_favorites()
        self.favorite_id_entry.delete(0, "end")
        self._fill_table()
        self.status_var.set(f"Предмет ID {item_id} удалён из избранного")

    def refresh_data(self):
        """Запускает сетевой запрос в фоне, не блокируя интерфейс."""
        url = self.url_entry.get().strip()
        if not url.lower().startswith(("http://", "https://")):
            messagebox.showerror(
                "Неверный адрес", "Введите полный URL, начинающийся с http:// или https://.",
                parent=self,
            )
            return

        auth_type = self.auth_menu.get()
        token = self.token_entry.get().strip()
        if auth_type != "Без авторизации" and not token:
            messagebox.showerror("Нет API-ключа", "Введите API-ключ.", parent=self)
            return

        self.refresh_button.configure(state="disabled", text="Загрузка…")
        self.status_var.set("Получение данных с сервера…")
        threading.Thread(
            target=self._request_worker, args=(url, auth_type, token), daemon=True
        ).start()

    def _request_worker(self, url, auth_type, token):
        headers = {"Accept": "application/json", "User-Agent": "ResaleCalculator/1.0"}
        if auth_type == "Bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "X-API-Key":
            headers["X-API-Key"] = token

        try:
            request = Request(url, headers=headers, method="GET")
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            normalized = self._normalize_api_data(data)
            self.after(0, lambda payload=normalized: self._request_complete(payload))
        except HTTPError as error:
            try:
                body = error.read().decode("utf-8", errors="replace").strip()
            except Exception:
                body = ""
            message = f"HTTP {error.code}: {error.reason}"
            if body:
                message += f"\n\nОтвет сервера: {body[:500]}"
            self.after(0, lambda text=message: self._request_failed(text))
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            message = str(error)
            self.after(0, lambda text=message: self._request_failed(text))
        except Exception as error:
            message = f"Непредвиденная ошибка: {error}"
            self.after(0, lambda text=message: self._request_failed(text))

    @staticmethod
    def _normalize_api_data(data):
        """Находит статистику в корне ответа или в распространённых оболочках."""
        def find_statistics(value):
            """Рекурсивно ищет объект, содержащий itemStatistics."""
            if isinstance(value, dict):
                if isinstance(value.get("itemStatistics"), list):
                    return value
                for nested in value.values():
                    found = find_statistics(nested)
                    if found is not None:
                        return found
            elif isinstance(value, list):
                for nested in value:
                    if isinstance(nested, dict):
                        found = find_statistics(nested)
                        if found is not None:
                            return found
            return None

        found = find_statistics(data)
        if found is not None:
            if found is not data and isinstance(data, dict):
                merged = dict(data)
                merged.update(found)
                return merged
            return found

        # Некоторые версии API возвращают предметы непосредственно в result.
        if isinstance(data, dict):
            for key in ("result", "data", "response", "payload"):
                nested = data.get(key)
                if isinstance(nested, list):
                    merged = dict(data)
                    merged["itemStatistics"] = nested
                    merged.setdefault("totalItems", len(nested))
                    return merged

            # Успешный ответ с result: null означает, что сервер не нашёл данных.
            if data.get("status") is True and data.get("result") is None:
                empty = dict(data)
                empty["itemStatistics"] = []
                empty["totalItems"] = 0
                empty["totalSold"] = 0
                return empty

        if isinstance(data, list):
            return {"itemStatistics": data, "totalItems": len(data)}

        if isinstance(data, dict):
            server_message = data.get("message") or data.get("error") or data.get("detail")
            if isinstance(server_message, dict):
                server_message = json.dumps(server_message, ensure_ascii=False)
            keys = ", ".join(map(str, data.keys())) or "нет полей"
            details = f"\nСообщение сервера: {server_message}" if server_message else ""
            if "status" in data:
                details += f"\nСтатус API: {data.get('status')}"
            if "code" in data:
                details += f"\nКод API: {data.get('code')}"
            result = data.get("result")
            if result is not None:
                preview = str(result)
                details += (
                    f"\nТип result: {type(result).__name__}"
                    f"\nСодержимое result: {preview[:300]}"
                )
            else:
                details += "\nПоле result пустое (null)"
            raise ValueError(
                f"В ответе нет массива itemStatistics.{details}\nПолученные поля: {keys}"
            )

        raise ValueError(
            f"Неожиданный формат ответа API: {type(data).__name__}"
        )

    def _request_complete(self, data):
        self.refresh_button.configure(state="normal", text="Обновить")
        self._apply_data(data)
        if data.get("result", object()) is None and not data.get("itemStatistics"):
            self.status_var.set("Запрос успешен, но API не вернул данные для этого сервера")
        else:
            self.status_var.set("Данные успешно обновлены и сохранены в локальный кэш")
        try:
            with open(self.cache_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except OSError:
            self.status_var.set("Данные обновлены, но локальный кэш сохранить не удалось")

    def _request_failed(self, text):
        self.refresh_button.configure(state="normal", text="Обновить")
        self.status_var.set("Ошибка обновления")
        messagebox.showerror("Ошибка API", text, parent=self)

    def _apply_data(self, data):
        self.items = data.get("itemStatistics", [])
        server_id = data.get("serverId", "—")
        server_name = data.get("serverName", "—")
        self.server_var.set(f"Сервер: {server_name} ({server_id})")
        self.updated_var.set(f"Обновлено: {self._format_date(data.get('lastUpdated'))}")
        self.summary_var.set(
            "Предметов: {}   Продано: {}   Средняя цена: {}".format(
                data.get("totalItems", "—"),
                data.get("totalSold", "—"),
                self._money(data.get("overallAveragePrice")),
            )
        )
        self._fill_table()

    def _fill_table(self):
        query = self.search_entry.get().strip().lower()
        only_favorites = self.only_favorites_var.get()
        for row in self.table.get_children():
            self.table.delete(row)
        for item in self.items:
            item_id = str(item.get("itemId", ""))
            name = str(item.get("itemName", ""))
            if query and query not in name.lower() and query not in item_id.lower():
                continue
            if only_favorites and item_id not in self.favorites:
                continue
            display_name = f"★ {name}" if item_id in self.favorites else name
            self.table.insert(
                "", "end",
                values=(
                    item_id, display_name, item.get("totalCount", "—"),
                    item.get("soldCount", "—"), self._money(item.get("averagePrice")),
                    self._money(item.get("minPrice")), self._money(item.get("maxPrice")),
                ),
            )

    def _load_cache(self):
        try:
            with open(self.cache_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict) and isinstance(data.get("itemStatistics"), list):
                self._apply_data(data)
                self.status_var.set("Показаны данные из локального кэша")
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass

    @staticmethod
    def _money(value):
        try:
            return f"{float(value):,.0f} ₽".replace(",", " ")
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _format_date(value):
        if not value:
            return "—"
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return str(value)


if __name__ == "__main__":
    app = App()
    app.mainloop()
