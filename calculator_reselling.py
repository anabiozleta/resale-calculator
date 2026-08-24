"""Десктопное приложение «Калькулятор перекупства»."""

import customtkinter as ctk
from tkinter import Menu, TclError, messagebox, ttk
import json
import os
import sys
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from datetime import datetime


# В обычном запуске данные лежат рядом со скриптом, в собранном EXE — рядом с EXE.
APP_DIR = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)


class App(ctk.CTk):
    """Главное окно калькулятора."""

    HISTORY_LIMIT = 100
    ACCENT = "#3b82f6"
    ACCENT_HOVER = "#2563eb"
    PROFIT = "#38d996"
    BG = "#080a0e"
    CARD = "#0e1117"
    CARD_ALT = "#121720"
    BORDER = "#252b36"
    TEXT = "#f5f7fa"
    MUTED = "#8993a4"
    ERROR = "#d64545"

    FIELDS = (
        ("purchase", "Цена покупки, ₽", ""),
        ("sale", "Цена продажи, ₽", ""),
        ("repair", "Ремонт, ₽", "0"),
        ("commission", "Комиссия, %", "0"),
        ("extra", "Другие расходы, ₽", "0"),
    )

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Калькулятор перекупства")
        self.geometry("1220x760")
        self.minsize(980, 680)
        self.configure(fg_color=self.BG)

        # История хранится рядом с программой.
        self.history_path = os.path.join(APP_DIR, "calculation_history.json")
        self.lots_path = os.path.join(APP_DIR, "active_lots.json")
        self.settings_path = os.path.join(APP_DIR, "app_settings.json")
        self.settings = self._load_settings()
        self.default_commission = float(self.settings.get("commission", 0))
        self.entries = {}
        self.active_lots = self._load_lots()
        self.selected_lot_id = None
        self.dashboard_vars = {
            "profit": ctk.StringVar(value="0 ₽"),
            "roi": ctk.StringVar(value="0.00 %"),
            "turnover": ctk.StringVar(value="0 ₽"),
        }
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
        self._refresh_active_lots()
        self._update_dashboard_totals()

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
            background=self.CARD_ALT,
            foreground=self.TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map("History.Treeview", background=[("selected", self.ACCENT)])

    def _shadow_card(self, parent, row, column, **grid_options):
        """Создаёт карточку с простой имитацией мягкой тени."""
        wrapper = ctk.CTkFrame(parent, fg_color=self.BORDER, corner_radius=12)
        wrapper.grid(row=row, column=column, **grid_options)
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)
        card = ctk.CTkFrame(wrapper, fg_color=self.CARD, corner_radius=11)
        card.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        return card

    def _build_interface(self):
        """Собирает все элементы главного окна."""
        self.grid_columnconfigure(0, weight=0, minsize=205)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(
            self, width=205, corner_radius=0, fg_color="#0b0e13",
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        ctk.CTkLabel(
            sidebar,
            text="FLIP\nDESK",
            justify="left",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
        ).pack(anchor="w", padx=22, pady=(26, 34))

        self.nav_buttons = {}
        def create_nav_button(key, label, symbol):
            button = ctk.CTkButton(
                sidebar,
                text=f"{symbol}   {label}",
                anchor="w",
                width=165,
                height=43,
                corner_radius=8,
                fg_color="transparent",
                hover_color=self.CARD_ALT,
                text_color=self.MUTED,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                command=lambda page=key: self.show_view(page),
            )
            self.nav_buttons[key] = button
            return button

        for key, label, symbol in (
            ("resale", "Перепродажа", "↗"),
            ("prices", "Прайс-лист", "≡"),
            ("rental", "Аренда авто", "◇"),
        ):
            create_nav_button(key, label, symbol).pack(padx=20, pady=4)

        ctk.CTkLabel(
            sidebar,
            text="Локальные данные\nбез облачного хранения",
            justify="left",
            text_color="#586273",
            font=("Segoe UI", 10),
        ).pack(side="bottom", anchor="w", padx=22, pady=22)

        create_nav_button("settings", "Настройки", "⚙").pack(
            side="bottom", padx=20, pady=(4, 0)
        )

        self.view_container = ctk.CTkFrame(self, fg_color="transparent")
        self.view_container.grid(row=0, column=1, sticky="nsew")
        self.view_container.grid_columnconfigure(0, weight=1)
        self.view_container.grid_rowconfigure(0, weight=1)

        self.resale_view = ctk.CTkFrame(self.view_container, fg_color="transparent")
        self.resale_view.grid(row=0, column=0, sticky="nsew")
        self.resale_view.grid_columnconfigure(0, weight=1)
        self.resale_view.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.resale_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 14))
        header.grid_columnconfigure(0, weight=1)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_box,
            text="Калькулятор сделок",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=30, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="Планируйте покупку, продажу и контролируйте доходность",
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        ).pack(anchor="w", pady=(3, 0))

        content = ctk.CTkFrame(self.resale_view, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=3)
        content.grid_rowconfigure(2, weight=2)

        stats_card = self._shadow_card(content, 0, 0, sticky="ew", pady=(0, 8))
        self._build_dashboard_stats(stats_card)

        work_area = ctk.CTkFrame(content, fg_color="transparent")
        work_area.grid(row=1, column=0, sticky="nsew", pady=8)
        work_area.grid_columnconfigure(0, weight=5, uniform="lots")
        work_area.grid_columnconfigure(1, weight=6, uniform="lots")
        work_area.grid_rowconfigure(0, weight=1)

        creator_card = self._shadow_card(
            work_area, 0, 0, sticky="nsew", padx=(0, 8)
        )
        active_card = self._shadow_card(
            work_area, 0, 1, sticky="nsew", padx=(8, 0)
        )
        self._build_lot_creator(creator_card)
        self._build_active_lots(active_card)

        log_card = self._shadow_card(content, 2, 0, sticky="nsew", pady=(8, 0))
        self._build_sales_log(log_card)

        self.price_view = PriceMonitorFrame(self.view_container, self)
        self.price_view.grid(row=0, column=0, sticky="nsew")
        self.rental_view = RentalFrame(self.view_container, self)
        self.rental_view.grid(row=0, column=0, sticky="nsew")
        self.settings_view = self._build_settings_view(self.view_container)
        self.settings_view.grid(row=0, column=0, sticky="nsew")
        self.show_view("resale")

    def show_view(self, name):
        """Переключает основной раздел через левое меню."""
        if name == "prices":
            self.price_view.tkraise()
        elif name == "rental":
            self.rental_view.tkraise()
        elif name == "settings":
            self.settings_view.tkraise()
        else:
            self.resale_view.tkraise()
            name = "resale"
        for key, button in self.nav_buttons.items():
            active = key == name
            button.configure(
                fg_color=self.CARD_ALT if active else "transparent",
                text_color=self.TEXT if active else self.MUTED,
                border_width=1 if active else 0,
                border_color=self.BORDER,
            )

    def _build_dashboard_stats(self, card):
        """Создаёт сводку по завершённым продажам."""
        for column in range(3):
            card.grid_columnconfigure(column, weight=1, uniform="dashboard")
        items = (
            ("profit", "ЧИСТЫЙ ДОХОД", self.PROFIT),
            ("roi", "ДОХОДНОСТЬ (ROI)", self.ACCENT),
            ("turnover", "ОБОРОТ", self.TEXT),
        )
        for column, (key, label, color) in enumerate(items):
            box = ctk.CTkFrame(card, fg_color="transparent")
            box.grid(row=0, column=column, sticky="ew", padx=20, pady=15)
            ctk.CTkLabel(
                box, text=label, text_color=self.MUTED,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            ).pack(anchor="w")
            ctk.CTkLabel(
                box, textvariable=self.dashboard_vars[key], text_color=color,
                font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            ).pack(anchor="w", pady=(2, 0))

    def _build_lot_creator(self, card):
        """Создаёт форму добавления предмета в активные лоты."""
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text="Добавление предмета", text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 5))
        ctk.CTkLabel(
            card,
            text="Создайте лот — продажу можно оформить позже в правой колонке.",
            text_color=self.MUTED, font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 15))

        self.lot_name_entry = ctk.CTkEntry(
            card, height=40, placeholder_text="Название предмета",
            fg_color=self.CARD_ALT, border_color=self.BORDER,
        )
        self.lot_name_entry.grid(row=2, column=0, sticky="ew", padx=20, pady=5)
        self.lot_purchase_entry = ctk.CTkEntry(
            card, height=40, placeholder_text="Сумма покупки, ₽",
            fg_color=self.CARD_ALT, border_color=self.BORDER,
        )
        self.lot_purchase_entry.grid(row=3, column=0, sticky="ew", padx=20, pady=5)
        self.lot_purchase_entry.bind("<Return>", lambda _event: self.add_lot())
        ctk.CTkButton(
            card, text="Добавить лот", height=42,
            fg_color=self.ACCENT, hover_color=self.ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.add_lot,
        ).grid(row=4, column=0, sticky="ew", padx=20, pady=(14, 10))
        self.direct_sale_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            card,
            text="Прямая продажа — без комиссии",
            variable=self.direct_sale_var,
            fg_color=self.PROFIT,
            hover_color="#24b879",
            border_color=self.BORDER,
            text_color=self.MUTED,
            font=("Segoe UI", 11),
        ).grid(row=5, column=0, sticky="w", padx=20, pady=(0, 20))

    def _build_active_lots(self, card):
        """Создаёт список непроданных лотов и панель оформления продажи."""
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=18, pady=(15, 8))
        ctk.CTkLabel(
            title_row, text="Активные лоты", text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left")
        self.lots_count_var = ctk.StringVar(value="0 предметов")
        ctk.CTkLabel(
            title_row, textvariable=self.lots_count_var, text_color=self.MUTED,
            font=("Segoe UI", 10),
        ).pack(side="right")

        self.active_lots_frame = ctk.CTkScrollableFrame(
            card, fg_color="transparent", scrollbar_button_color=self.BORDER,
            scrollbar_button_hover_color=self.ACCENT,
        )
        self.active_lots_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=0)
        self.active_lots_frame.grid_columnconfigure(0, weight=1)

        self.sale_panel = ctk.CTkFrame(
            card, fg_color=self.CARD_ALT, corner_radius=8,
            border_width=1, border_color=self.BORDER,
        )
        self.sale_panel.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        self.sale_panel.grid_columnconfigure(0, weight=1)
        self.selected_lot_var = ctk.StringVar(value="Выберите лот для продажи")
        ctk.CTkLabel(
            self.sale_panel, textvariable=self.selected_lot_var,
            text_color=self.TEXT, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 7))
        self.sale_price_entry = ctk.CTkEntry(
            self.sale_panel, height=36, placeholder_text="Сумма продажи, ₽",
            fg_color=self.CARD, border_color=self.BORDER, state="disabled",
        )
        self.sale_price_entry.grid(row=1, column=0, sticky="ew", padx=(12, 6), pady=(0, 11))
        self.sale_price_entry.bind("<Return>", lambda _event: self.sell_selected_lot())
        self.sell_button = ctk.CTkButton(
            self.sale_panel, text="Продать", width=100, height=36,
            fg_color=self.PROFIT, hover_color="#24b879", text_color="#06120d",
            state="disabled", command=self.sell_selected_lot,
        )
        self.sell_button.grid(row=1, column=1, padx=(6, 12), pady=(0, 11))

    def _build_sales_log(self, card):
        """Создаёт журнал завершённых сделок."""
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(11, 7))
        ctk.CTkLabel(
            header, text="Логи продаж", text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header, text="Удалить продажу", width=135, height=31,
            fg_color="transparent", hover_color="#3a2024",
            border_width=1, border_color=self.BORDER, text_color=self.MUTED,
            command=self.delete_selected_sale,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            header, text="Очистить все логи", width=135, height=31,
            fg_color="transparent", hover_color="#3a2024",
            border_width=1, border_color=self.BORDER, text_color=self.MUTED,
            command=self.clear_history,
        ).pack(side="right")
        columns = ("time", "item", "purchase", "sale", "profit", "roi")
        self.history_table = ttk.Treeview(
            card, columns=columns, show="headings", style="History.Treeview", height=6
        )
        headings = {
            "time": "Дата", "item": "Предмет", "purchase": "Покупка",
            "sale": "Продажа", "profit": "Чистая прибыль", "roi": "ROI",
        }
        widths = {
            "time": 125, "item": 220, "purchase": 120,
            "sale": 120, "profit": 135, "roi": 85,
        }
        for column in columns:
            self.history_table.heading(column, text=headings[column])
            self.history_table.column(
                column, width=widths[column], anchor="w" if column == "item" else "center"
            )
        self.history_table.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))

    def _build_settings_view(self, parent):
        """Создаёт раздел общих настроек калькулятора."""
        view = ctk.CTkFrame(parent, fg_color="transparent")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 18))
        ctk.CTkLabel(
            header,
            text="Настройки",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=30, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Общие параметры, используемые при расчёте сделок",
            text_color=self.MUTED,
            font=("Segoe UI", 13),
        ).pack(anchor="w", pady=(3, 0))

        area = ctk.CTkFrame(view, fg_color="transparent")
        area.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        area.grid_columnconfigure(0, weight=1)
        card = self._shadow_card(area, 0, 0, sticky="new")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text="Комиссия с продажи",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 4))
        ctk.CTkLabel(
            card,
            text="Процент рассчитывается от цены продажи и включается в общие расходы.",
            text_color=self.MUTED,
            font=("Segoe UI", 11),
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 16))

        input_row = ctk.CTkFrame(card, fg_color="transparent")
        input_row.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))
        self.settings_commission_entry = ctk.CTkEntry(
            input_row,
            width=180,
            height=40,
            fg_color=self.CARD_ALT,
            border_color=self.BORDER,
            placeholder_text="0",
        )
        self.settings_commission_entry.pack(side="left")
        self.settings_commission_entry.insert(
            0, self._plain_number(self.default_commission)
        )
        ctk.CTkLabel(
            input_row, text="%", text_color=self.MUTED, font=("Segoe UI", 14)
        ).pack(side="left", padx=(8, 18))
        ctk.CTkButton(
            input_row,
            text="Сохранить",
            width=125,
            height=40,
            fg_color=self.ACCENT,
            hover_color=self.ACCENT_HOVER,
            command=self.save_settings,
        ).pack(side="left")

        self.settings_status_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            card,
            textvariable=self.settings_status_var,
            text_color=self.PROFIT,
            font=("Segoe UI", 11),
        ).grid(row=3, column=0, sticky="w", padx=22, pady=(0, 20))
        return view

    def _load_settings(self):
        try:
            with open(self.settings_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def save_settings(self):
        """Проверяет и сохраняет комиссию, затем применяет её к форме сделки."""
        try:
            commission = self._parse_number(self.settings_commission_entry.get())
            if commission > 100:
                raise ValueError
        except ValueError:
            self.settings_commission_entry.configure(
                border_color=self.ERROR, border_width=2
            )
            messagebox.showerror(
                "Ошибка ввода",
                "Комиссия должна быть числом от 0 до 100.",
                parent=self,
            )
            return

        self.default_commission = commission
        self.settings["commission"] = commission
        try:
            with open(self.settings_path, "w", encoding="utf-8") as file:
                json.dump(self.settings, file, ensure_ascii=False, indent=2)
        except OSError as error:
            messagebox.showerror(
                "Настройки не сохранены", f"Не удалось сохранить настройки:\n{error}",
                parent=self,
            )
            return

        self.settings_commission_entry.configure(border_color=self.BORDER, border_width=2)
        self.settings_status_var.set("Комиссия сохранена и будет применена при продаже лота")

    @staticmethod
    def _plain_number(value):
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number).replace(".", ",")

    def _build_input_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            card,
            text="Новая сделка",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))

        # Прокручиваемая область сохраняет доступ ко всем полям в низком окне.
        fields_frame = ctk.CTkScrollableFrame(
            card,
            fg_color="transparent",
            scrollbar_button_color=self.BORDER,
            scrollbar_button_hover_color=self.ACCENT,
        )
        fields_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 5), pady=(0, 10))
        fields_frame.grid_columnconfigure(0, weight=1, uniform="fields")
        fields_frame.grid_columnconfigure(1, weight=1, uniform="fields")

        ctk.CTkLabel(
            fields_frame,
            text="Предмет сделки",
            text_color=self.TEXT,
            font=("Segoe UI", 12),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(7, 3))
        self.item_name_entry = ctk.CTkEntry(
            fields_frame,
            height=39,
            fg_color=self.CARD_ALT,
            border_color=self.BORDER,
            text_color=self.TEXT,
            placeholder_text="Например: ID-карта",
        )
        self.item_name_entry.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 6)
        )
        self.item_name_entry.bind("<Return>", lambda _event: self.calculate())

        for index, (key, label, default) in enumerate(self.FIELDS):
            column = index % 2
            field_row = (index // 2) * 2 + 2
            ctk.CTkLabel(
                fields_frame, text=label, text_color=self.TEXT, font=("Segoe UI", 12)
            ).grid(
                row=field_row, column=column, sticky="w",
                padx=(16 if column == 0 else 8, 16), pady=(7, 3),
            )
            entry = ctk.CTkEntry(
                fields_frame,
                height=39,
                fg_color=self.CARD_ALT,
                border_color=self.BORDER,
                text_color=self.TEXT,
                placeholder_text="0",
            )
            entry.grid(
                row=field_row + 1, column=column, sticky="ew",
                padx=(16 if column == 0 else 8, 16), pady=(0, 6),
            )
            if default:
                value = self.default_commission if key == "commission" else default
                entry.insert(0, self._plain_number(value))
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
        ).grid(row=9, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 14))

    def _build_result_card(self, card):
        for column in range(4):
            card.grid_columnconfigure(column, weight=1, uniform="stats")
        ctk.CTkLabel(
            card,
            text="Итог сделки",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(16, 10))

        items = (
            ("expenses", "РАСХОДЫ", self.TEXT),
            ("profit", "ЧИСТАЯ ПРИБЫЛЬ", self.PROFIT),
            ("margin", "МАРЖА", self.ACCENT),
            ("roi", "ROI", self.PROFIT),
        )
        for column, (key, label, color) in enumerate(items):
            box = ctk.CTkFrame(
                card, fg_color=self.CARD_ALT, corner_radius=8,
                border_width=1, border_color=self.BORDER,
            )
            box.grid(
                row=1, column=column, sticky="nsew",
                padx=(20 if column == 0 else 5, 20 if column == 3 else 5), pady=0,
            )
            box.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                box, text=label, text_color=self.MUTED,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=13, pady=(11, 1))
            ctk.CTkLabel(
                box,
                textvariable=self.result_vars[key],
                text_color=color,
                font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
            ).grid(row=1, column=0, sticky="w", padx=13, pady=(1, 12))

        ctk.CTkLabel(
            card,
            text="Комиссия считается от цены продажи",
            text_color=self.MUTED,
            font=("Segoe UI", 10),
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=20, pady=(12, 14))

        ctk.CTkButton(
            card,
            text="Сбросить",
            width=100,
            height=30,
            fg_color="transparent",
            hover_color=self.CARD_ALT,
            border_width=1,
            border_color=self.BORDER,
            text_color=self.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self.reset_results,
        ).grid(row=2, column=3, sticky="e", padx=20, pady=(10, 12))

    def _build_history_card(self, card):
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 8))
        ctk.CTkLabel(
            title_row,
            text="История сделок",
            text_color=self.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            title_row,
            text="Очистить",
            width=85,
            height=30,
            fg_color="transparent",
            hover_color=self.CARD_ALT,
            border_width=1,
            border_color=self.BORDER,
            text_color=self.MUTED,
            command=self.clear_history,
        ).pack(side="right")

        columns = ("time", "deal", "profit", "roi")
        self.history_table = ttk.Treeview(
            card, columns=columns, show="headings", height=12, style="History.Treeview"
        )
        headings = {
            "time": "Дата",
            "deal": "Покупка → продажа",
            "profit": "Прибыль",
            "roi": "ROI",
        }
        widths = {"time": 105, "deal": 230, "profit": 105, "roi": 65}
        for column in columns:
            self.history_table.heading(column, text=headings[column])
            self.history_table.column(column, width=widths[column], anchor="center")
        self.history_table.grid(row=1, column=0, sticky="nsew", padx=16, pady=(4, 16))

    @staticmethod
    def _parse_number(value):
        """Преобразует число, разрешая пробелы и запятую как разделитель."""
        cleaned = value.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        number = float(cleaned)
        if number < 0:
            raise ValueError
        return number

    def _reset_entry(self, entry):
        entry.configure(border_color=self.BORDER)

    def reset_results(self):
        """Очищает рассчитанные показатели, не затрагивая историю."""
        for variable in self.result_vars.values():
            variable.set("—")

    def open_price_monitor(self):
        """Переключает интерфейс на встроенный прайс-лист."""
        self.show_view("prices")

    def add_lot(self):
        """Добавляет купленный предмет в список активных лотов."""
        name = self.lot_name_entry.get().strip()
        try:
            purchase = self._parse_number(self.lot_purchase_entry.get())
        except ValueError:
            self.lot_purchase_entry.configure(border_color=self.ERROR, border_width=2)
            messagebox.showerror(
                "Ошибка ввода", "Сумма покупки должна быть числом не меньше нуля.", parent=self
            )
            return
        if not name:
            self.lot_name_entry.configure(border_color=self.ERROR, border_width=2)
            messagebox.showerror("Нет названия", "Введите название предмета.", parent=self)
            return

        lot = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "name": name,
            "purchase": purchase,
            "direct_sale": bool(self.direct_sale_var.get()),
            "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        }
        self.active_lots.insert(0, lot)
        self._save_lots()
        self.lot_name_entry.delete(0, "end")
        self.lot_purchase_entry.delete(0, "end")
        self.direct_sale_var.set(False)
        self.lot_name_entry.configure(border_color=self.BORDER)
        self.lot_purchase_entry.configure(border_color=self.BORDER)
        self._refresh_active_lots()
        self.select_lot(lot["id"])

    def select_lot(self, lot_id):
        """Выбирает лот и открывает ввод цены продажи."""
        lot = next((item for item in self.active_lots if item.get("id") == lot_id), None)
        if not lot:
            return
        self.selected_lot_id = lot_id
        sale_mode = "  ·  без комиссии" if lot.get("direct_sale", False) else ""
        self.selected_lot_var.set(
            f'{lot.get("name", "Предмет")}  ·  куплено за '
            f'{self._format_money(float(lot["purchase"]))}{sale_mode}'
        )
        self.sale_price_entry.configure(state="normal", border_color=self.BORDER)
        self.sell_button.configure(state="normal")
        self.sale_price_entry.delete(0, "end")
        self.sale_price_entry.focus_set()
        self._refresh_active_lots()

    def delete_lot(self, lot_id):
        """Удаляет непроданный лот после подтверждения."""
        lot = next((item for item in self.active_lots if item.get("id") == lot_id), None)
        if not lot:
            return
        if not messagebox.askyesno(
            "Удаление лота", f'Удалить «{lot.get("name", "Предмет")}»?', parent=self
        ):
            return
        self.active_lots = [item for item in self.active_lots if item.get("id") != lot_id]
        if self.selected_lot_id == lot_id:
            self._clear_lot_selection()
        self._save_lots()
        self._refresh_active_lots()

    def sell_selected_lot(self):
        """Закрывает выбранный лот и рассчитывает результат продажи."""
        lot = next(
            (item for item in self.active_lots if item.get("id") == self.selected_lot_id),
            None,
        )
        if not lot:
            return
        try:
            sale = self._parse_number(self.sale_price_entry.get())
        except ValueError:
            self.sale_price_entry.configure(border_color=self.ERROR, border_width=2)
            messagebox.showerror(
                "Ошибка ввода", "Сумма продажи должна быть числом не меньше нуля.", parent=self
            )
            return

        purchase = float(lot["purchase"])
        commission_percent = 0 if lot.get("direct_sale", False) else self.default_commission
        commission_rub = sale * commission_percent / 100
        expenses = purchase + commission_rub
        profit = sale - expenses
        roi = profit / expenses * 100 if expenses else 0
        margin = profit / sale * 100 if sale else 0
        record = {
            "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "item_name": lot.get("name", "Без названия"),
            "purchase": purchase,
            "sale": sale,
            "commission_percent": commission_percent,
            "commission_rub": commission_rub,
            "expenses": expenses,
            "profit": profit,
            "margin": margin,
            "roi": roi,
        }
        self.history.insert(0, record)
        self.history = self.history[: self.HISTORY_LIMIT]
        self.active_lots = [
            item for item in self.active_lots if item.get("id") != self.selected_lot_id
        ]
        self._save_history()
        self._save_lots()
        self._clear_lot_selection()
        self._refresh_active_lots()
        self._refresh_history_table()
        self._update_dashboard_totals()

    def _clear_lot_selection(self):
        self.selected_lot_id = None
        self.selected_lot_var.set("Выберите лот для продажи")
        self.sale_price_entry.configure(state="normal")
        self.sale_price_entry.delete(0, "end")
        self.sale_price_entry.configure(state="disabled", border_color=self.BORDER)
        self.sell_button.configure(state="disabled")

    def _refresh_active_lots(self):
        """Перерисовывает карточки активных лотов."""
        for widget in self.active_lots_frame.winfo_children():
            widget.destroy()
        self.lots_count_var.set(f"{len(self.active_lots)} шт.")
        if not self.active_lots:
            ctk.CTkLabel(
                self.active_lots_frame,
                text="Нет активных лотов\nДобавьте первый предмет слева",
                justify="center", text_color=self.MUTED, font=("Segoe UI", 12),
            ).grid(row=0, column=0, sticky="ew", pady=28)
            return

        for row, lot in enumerate(self.active_lots):
            selected = lot.get("id") == self.selected_lot_id
            item = ctk.CTkFrame(
                self.active_lots_frame,
                fg_color="#18202b" if selected else self.CARD_ALT,
                corner_radius=8, border_width=1,
                border_color=self.ACCENT if selected else self.BORDER,
            )
            item.grid(row=row, column=0, sticky="ew", padx=3, pady=4)
            item.grid_columnconfigure(0, weight=1)
            ctk.CTkButton(
                item,
                text="{}{}\nКуплено: {}".format(
                    lot.get("name", "Предмет"),
                    "  ·  без комиссии" if lot.get("direct_sale", False) else "",
                    self._format_money(float(lot.get("purchase", 0))),
                ),
                anchor="w", height=54, fg_color="transparent",
                hover_color="#1c2633", text_color=self.TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda lot_id=lot.get("id"): self.select_lot(lot_id),
            ).grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=3)
            ctk.CTkButton(
                item, text="×", width=34, height=34,
                fg_color="transparent", hover_color="#3a2024", text_color=self.MUTED,
                command=lambda lot_id=lot.get("id"): self.delete_lot(lot_id),
            ).grid(row=0, column=1, padx=7)

    def _update_dashboard_totals(self):
        """Пересчитывает сводные показатели по завершённым сделкам."""
        profit = sum(float(item.get("profit", 0)) for item in self.history)
        turnover = sum(float(item.get("sale", 0)) for item in self.history)
        expenses = sum(
            float(item.get("expenses", float(item.get("sale", 0)) - float(item.get("profit", 0))))
            for item in self.history
        )
        roi = profit / expenses * 100 if expenses else 0
        self.dashboard_vars["profit"].set(self._format_money(profit))
        self.dashboard_vars["turnover"].set(self._format_money(turnover))
        self.dashboard_vars["roi"].set(f"{roi:,.2f} %".replace(",", " "))

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
            "item_name": self.item_name_entry.get().strip() or "Без названия",
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

    def _load_lots(self):
        """Загружает непроданные лоты из локального файла."""
        try:
            with open(self.lots_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _save_lots(self):
        try:
            with open(self.lots_path, "w", encoding="utf-8") as file:
                json.dump(self.active_lots, file, ensure_ascii=False, indent=2)
        except OSError as error:
            messagebox.showwarning(
                "Лоты не сохранены", f"Не удалось сохранить активные лоты:\n{error}",
                parent=self,
            )

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
        for index, record in enumerate(self.history):
            try:
                self.history_table.insert(
                    "",
                    "end",
                    iid=str(index),
                    values=(
                        record["time"],
                        record.get("item_name", "Сделка"),
                        self._format_money(float(record["purchase"])),
                        self._format_money(float(record["sale"])),
                        self._format_money(float(record["profit"])),
                        f'{float(record["roi"]):,.2f} %'.replace(",", " "),
                    ),
                )
            except (KeyError, TypeError, ValueError):
                continue

    def delete_selected_sale(self):
        """Удаляет выбранную завершённую сделку из журнала."""
        selection = self.history_table.selection()
        if not selection:
            messagebox.showinfo(
                "Удаление продажи", "Сначала выберите продажу в таблице.", parent=self
            )
            return
        try:
            index = int(selection[0])
            record = self.history[index]
        except (ValueError, IndexError):
            return
        if not messagebox.askyesno(
            "Удаление продажи",
            f'Удалить продажу «{record.get("item_name", "Без названия")}»?',
            parent=self,
        ):
            return
        self.history.pop(index)
        self._save_history()
        self._refresh_history_table()
        self._update_dashboard_totals()

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
            self._update_dashboard_totals()


class RentalFrame(ctk.CTkFrame):
    """Раздел учёта автопарка, доходов и расходов от аренды."""

    LISTING_DAY_COST = 500

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=app.BG, corner_radius=0)
        self.app = app
        self.data_path = os.path.join(APP_DIR, "rental_data.json")
        self.data = self._load_data()
        self.selected_days = 1
        self.rate_unit = "day"
        self.selected_car_id = None
        self.income_var = ctk.StringVar(value="0 ₽")
        self.expense_var = ctk.StringVar(value="0 ₽")
        self.deals_var = ctk.StringVar(value="0")
        self.listing_total_var = ctk.StringVar(value="500 ₽")
        self._build_interface()
        self._refresh_all()

    def _build_interface(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        page = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=self.app.BORDER,
            scrollbar_button_hover_color=self.app.ACCENT,
        )
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, minsize=340)
        page.grid_rowconfigure(3, minsize=260)

        ctk.CTkLabel(
            page, text="Аренда авто", text_color=self.app.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=30, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 14))

        stats = self.app._shadow_card(page, 1, 0, sticky="ew", padx=24, pady=(0, 8))
        for column in range(3):
            stats.grid_columnconfigure(column, weight=1, uniform="rental_stats")
        for column, (label, variable, color) in enumerate((
            ("ЧИСТЫЙ ДОХОД", self.income_var, self.app.PROFIT),
            ("РАСХОД", self.expense_var, self.app.ERROR),
            ("СДЕЛКИ", self.deals_var, self.app.TEXT),
        )):
            box = ctk.CTkFrame(stats, fg_color="transparent")
            box.grid(row=0, column=column, sticky="ew", padx=20, pady=14)
            ctk.CTkLabel(
                box, text=label, text_color=self.app.MUTED,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            ).pack(anchor="w")
            ctk.CTkLabel(
                box, textvariable=variable, text_color=color,
                font=ctk.CTkFont(family="Segoe UI", size=23, weight="bold"),
            ).pack(anchor="w", pady=(2, 0))

        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=24, pady=8)
        body.grid_columnconfigure(0, weight=1, uniform="rental_body")
        body.grid_columnconfigure(1, weight=1, uniform="rental_body")
        body.grid_rowconfigure(0, weight=1)
        left = self.app._shadow_card(body, 0, 0, sticky="nsew", padx=(0, 8))
        right = self.app._shadow_card(body, 0, 1, sticky="nsew", padx=(8, 0))
        self._build_car_form(left)
        self._build_fleet(right)

        logs = self.app._shadow_card(page, 3, 0, sticky="nsew", padx=24, pady=(8, 24))
        self._build_rental_logs(logs)

    def _build_car_form(self, card):
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text="Добавление авто", text_color=self.app.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(17, 10))

        mode_row = ctk.CTkFrame(card, fg_color="transparent")
        mode_row.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 7))
        self.rate_unit_buttons = {}
        for unit, label in (("hour", "По часам"), ("day", "Посуточно")):
            button = ctk.CTkButton(
                mode_row, text=label, width=105, height=32,
                fg_color="transparent", hover_color=self.app.CARD_ALT,
                border_width=1, border_color=self.app.BORDER,
                command=lambda value=unit: self._select_rate_unit(value),
            )
            button.pack(side="left", padx=(0, 7))
            self.rate_unit_buttons[unit] = button
        self.car_name_entry = ctk.CTkEntry(
            card, height=38, placeholder_text="Название автомобиля",
            fg_color=self.app.CARD_ALT, border_color=self.app.BORDER,
        )
        self.car_name_entry.grid(row=2, column=0, sticky="ew", padx=20, pady=4)
        self.car_rate_entry = ctk.CTkEntry(
            card, height=38, placeholder_text="Стоимость аренды за сутки, ₽",
            fg_color=self.app.CARD_ALT, border_color=self.app.BORDER,
        )
        self.car_rate_entry.grid(row=3, column=0, sticky="ew", padx=20, pady=4)
        ctk.CTkLabel(
            card, text="Срок подачи объявления, дней", text_color=self.app.MUTED,
            font=("Segoe UI", 11),
        ).grid(row=4, column=0, sticky="w", padx=20, pady=(11, 5))
        days_row = ctk.CTkFrame(card, fg_color="transparent")
        days_row.grid(row=5, column=0, sticky="w", padx=20)
        self.day_buttons = {}
        for day in range(1, 8):
            button = ctk.CTkButton(
                days_row, text=str(day), width=38, height=34,
                fg_color="transparent", hover_color=self.app.CARD_ALT,
                border_width=1, border_color=self.app.BORDER,
                command=lambda value=day: self._select_days(value),
            )
            button.pack(side="left", padx=(0, 6))
            self.day_buttons[day] = button
        self._select_days(1)
        ctk.CTkLabel(
            card, text="Стоимость объявления", text_color=self.app.MUTED,
            font=("Segoe UI", 10),
        ).grid(row=6, column=0, sticky="w", padx=20, pady=(12, 0))
        self.listing_cost_entry = ctk.CTkEntry(
            card, height=38, fg_color=self.app.CARD_ALT,
            border_color=self.app.BORDER, placeholder_text="Стоимость публикации, ₽",
        )
        self.listing_cost_entry.grid(row=7, column=0, sticky="ew", padx=20, pady=(3, 8))
        self.listing_cost_entry.insert(0, str(self.LISTING_DAY_COST))
        ctk.CTkButton(
            card, text="Добавить в автопарк", height=38,
            fg_color=self.app.ACCENT, hover_color=self.app.ACCENT_HOVER,
            command=self.add_car,
        ).grid(row=8, column=0, sticky="ew", padx=20, pady=(4, 16))
        self._select_rate_unit("day")

    def _build_fleet(self, card):
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            card, text="Автопарк", text_color=self.app.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(15, 7))
        self.fleet_frame = ctk.CTkScrollableFrame(
            card, fg_color="transparent", scrollbar_button_color=self.app.BORDER,
            scrollbar_button_hover_color=self.app.ACCENT,
        )
        self.fleet_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.fleet_frame.grid_columnconfigure(0, weight=1)

    def _build_rental_logs(self, card):
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))
        ctk.CTkLabel(
            header, text="Логи аренды", text_color=self.app.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header, text="Очистить логи", width=110, height=29,
            fg_color="transparent", hover_color="#3a2024",
            border_width=1, border_color=self.app.BORDER,
            command=self.clear_logs,
        ).pack(side="right")
        columns = ("date", "car", "days", "amount")
        self.log_table = ttk.Treeview(
            card, columns=columns, show="headings", style="History.Treeview", height=5
        )
        for column, label, width in (
            ("date", "Дата", 150), ("car", "Автомобиль", 420),
            ("days", "Срок аренды", 130), ("amount", "Доход", 160),
        ):
            self.log_table.heading(column, text=label)
            self.log_table.column(
                column, width=width, anchor="w" if column == "car" else "center"
            )
        self.log_table.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

    def _select_rate_unit(self, unit):
        """Переключает почасовой и посуточный тариф."""
        self.rate_unit = unit
        if hasattr(self, "car_rate_entry"):
            placeholder = (
                "Стоимость аренды за час, ₽"
                if unit == "hour"
                else "Стоимость аренды за сутки, ₽"
            )
            self.car_rate_entry.configure(placeholder_text=placeholder)
        for value, button in self.rate_unit_buttons.items():
            button.configure(
                fg_color=self.app.TEXT if value == unit else "transparent",
                text_color=self.app.BG if value == unit else self.app.TEXT,
            )

    def _select_days(self, days):
        self.selected_days = days
        self.listing_total_var.set(self.app._format_money(days * self.LISTING_DAY_COST))
        if hasattr(self, "listing_cost_entry"):
            self.listing_cost_entry.delete(0, "end")
            self.listing_cost_entry.insert(0, str(days * self.LISTING_DAY_COST))
        for value, button in self.day_buttons.items():
            button.configure(
                fg_color=self.app.TEXT if value == days else "transparent",
                text_color=self.app.BG if value == days else self.app.TEXT,
            )

    def add_car(self):
        name = self.car_name_entry.get().strip()
        try:
            rate = self.app._parse_number(self.car_rate_entry.get())
            listing_cost = self.app._parse_number(self.listing_cost_entry.get())
        except ValueError:
            messagebox.showerror(
                "Ошибка", "Введите корректную стоимость аренды и публикации.", parent=self
            )
            return
        if not name:
            messagebox.showerror("Ошибка", "Введите название автомобиля.", parent=self)
            return
        car = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "name": name, "daily_rate": rate, "rate_unit": self.rate_unit,
            "listing_days": self.selected_days,
        }
        self.data["cars"].insert(0, car)
        self.data["listing_expenses"] = float(self.data.get("listing_expenses", 0)) + listing_cost
        self.car_name_entry.delete(0, "end")
        self.car_rate_entry.delete(0, "end")
        self._save_data()
        self._refresh_all()

    def remove_car(self, car_id):
        car = next((item for item in self.data["cars"] if item.get("id") == car_id), None)
        if not car or not messagebox.askyesno(
            "Удаление авто", f'Удалить «{car.get("name", "Авто")}» из автопарка?', parent=self
        ):
            return
        self.data["cars"] = [item for item in self.data["cars"] if item.get("id") != car_id]
        if self.selected_car_id == car_id:
            self.selected_car_id = None
        self._save_data()
        self._refresh_fleet()

    def select_rental_car(self, car_id):
        """Раскрывает выбранную карточку автомобиля для оформления аренды."""
        self.selected_car_id = None if self.selected_car_id == car_id else car_id
        self._refresh_fleet()
        if self.selected_car_id and hasattr(self, "rental_duration_entry"):
            self.rental_duration_entry.focus_set()

    def complete_rental(self):
        """Рассчитывает доход по тарифу и длительности выбранного автомобиля."""
        car = next(
            (item for item in self.data["cars"] if item.get("id") == self.selected_car_id),
            None,
        )
        if not car:
            return
        try:
            duration = self.app._parse_number(self.rental_duration_entry.get())
            if duration <= 0:
                raise ValueError
        except ValueError:
            unit_name = "часов" if car.get("rate_unit", "day") == "hour" else "суток"
            messagebox.showerror(
                "Ошибка", f"Количество {unit_name} должно быть числом больше нуля.", parent=self
            )
            return
        rate_unit = car.get("rate_unit", "day")
        amount = float(car.get("daily_rate", 0)) * duration
        self.data["logs"].insert(0, {
            "kind": "rental",
            "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "car_id": car.get("id"),
            "car_name": car.get("name", "Авто"),
            "days": duration,
            "duration_unit": rate_unit,
            "amount": amount,
        })
        self.selected_car_id = None
        self._save_data()
        self._refresh_all()

    def _refresh_all(self):
        self._refresh_fleet()
        self._refresh_logs()
        income = sum(float(item.get("amount", 0)) for item in self.data["logs"])
        expense = float(self.data.get("listing_expenses", 0))
        deals = len(self.data["logs"])
        self.income_var.set(self.app._format_money(income - expense))
        self.expense_var.set(self.app._format_money(expense))
        self.deals_var.set(str(deals))

    def _refresh_fleet(self):
        for widget in self.fleet_frame.winfo_children():
            widget.destroy()
        if not self.data["cars"]:
            ctk.CTkLabel(
                self.fleet_frame, text="Нет автомобилей", text_color=self.app.MUTED
            ).grid(row=0, column=0, pady=28)
            return
        for row, car in enumerate(self.data["cars"]):
            selected = car.get("id") == self.selected_car_id
            item = ctk.CTkFrame(
                self.fleet_frame,
                fg_color="#18202b" if selected else self.app.CARD_ALT,
                border_width=1,
                border_color=self.app.ACCENT if selected else self.app.BORDER,
                corner_radius=8,
            )
            item.grid(row=row, column=0, sticky="ew", padx=3, pady=4)
            item.grid_columnconfigure(0, weight=1)
            ctk.CTkButton(
                item,
                text="{}\n{} / {}  ·  объявление {} дн.".format(
                    car.get("name", "Авто"),
                    self.app._format_money(float(car.get("daily_rate", 0))),
                    "час" if car.get("rate_unit", "day") == "hour" else "сутки",
                    car.get("listing_days", 1),
                ),
                anchor="w", height=58, fg_color="transparent",
                hover_color="#1c2633", text_color=self.app.TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda car_id=car.get("id"): self.select_rental_car(car_id),
            ).grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=3)
            ctk.CTkLabel(
                item, text="Свободен", text_color=self.app.PROFIT,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            ).grid(row=0, column=1, padx=6)
            ctk.CTkButton(
                item, text="×", width=32, height=32, fg_color="transparent",
                hover_color="#3a2024", text_color=self.app.MUTED,
                command=lambda car_id=car.get("id"): self.remove_car(car_id),
            ).grid(row=0, column=2, padx=(2, 8))
            if selected:
                unit_text = "часов" if car.get("rate_unit", "day") == "hour" else "суток"
                self.rental_duration_entry = ctk.CTkEntry(
                    item, height=36, placeholder_text=f"Количество {unit_text}",
                    fg_color=self.app.CARD, border_color=self.app.BORDER,
                )
                self.rental_duration_entry.grid(
                    row=1, column=0, columnspan=2, sticky="ew",
                    padx=(12, 6), pady=(0, 11),
                )
                self.rental_duration_entry.bind(
                    "<Return>", lambda _event: self.complete_rental()
                )
                ctk.CTkButton(
                    item, text="Сдать", width=85, height=36,
                    fg_color=self.app.TEXT, hover_color="#d6d9de",
                    text_color=self.app.BG, command=self.complete_rental,
                ).grid(row=1, column=2, padx=(6, 8), pady=(0, 11))

    def _refresh_logs(self):
        for row in self.log_table.get_children():
            self.log_table.delete(row)
        for log in self.data["logs"]:
            amount = float(log.get("amount", 0))
            duration_suffix = "ч." if log.get("duration_unit") == "hour" else "сут."
            self.log_table.insert("", "end", values=(
                log.get("date", "—"), log.get("car_name", "Автомобиль"),
                f'{self.app._plain_number(log.get("days", 0))} {duration_suffix}',
                self.app._format_money(amount),
            ))

    def clear_logs(self):
        if self.data["logs"] and messagebox.askyesno(
            "Очистка логов", "Удалить все логи аренды?", parent=self
        ):
            self.data["logs"] = []
            self._save_data()
            self._refresh_all()

    def _load_data(self):
        try:
            with open(self.data_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                data.setdefault("cars", [])
                data.setdefault("logs", [])
                if data.get("schema_version", 1) < 2:
                    # Старые ручные операции удаляются: журнал теперь только об аренде.
                    old_expenses = -sum(
                        float(item.get("amount", 0))
                        for item in data["logs"]
                        if float(item.get("amount", 0)) < 0
                    )
                    data["listing_expenses"] = old_expenses
                    data["logs"] = []
                    data["schema_version"] = 2
                    try:
                        with open(self.data_path, "w", encoding="utf-8") as file:
                            json.dump(data, file, ensure_ascii=False, indent=2)
                    except OSError:
                        pass
                data.setdefault("listing_expenses", 0)
                return data
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
        return {"cars": [], "logs": [], "listing_expenses": 0, "schema_version": 2}

    def _save_data(self):
        try:
            with open(self.data_path, "w", encoding="utf-8") as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
        except OSError as error:
            messagebox.showwarning(
                "Данные не сохранены", f"Не удалось сохранить данные аренды:\n{error}",
                parent=self,
            )


class PriceMonitorFrame(ctk.CTkFrame):
    """Встроенный раздел получения и просмотра статистики цен."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=app.BG, corner_radius=0)
        self.parent = app
        self.items = []
        self.cache_path = os.path.join(APP_DIR, "marketplace_cache.json")
        self.favorites_path = os.path.join(APP_DIR, "marketplace_favorites.json")
        self.favorites = self._load_favorites()

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
            text="Прайс-лист",
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
