import sys
import ccxt
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QVBoxLayout, 
                           QHBoxLayout, QWidget, QLabel, QPushButton, QTableWidget,
                           QTableWidgetItem, QDoubleSpinBox, QComboBox, QStatusBar,
                           QMessageBox, QLineEdit, QFormLayout, QGroupBox)
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
from PyQt5.QtCore import Qt, QTimer, QDateTime, QSettings
from PyQt5.QtGui import QFont, QPainter  # اضافه کردن QPainter

class TradingEngine:
    def __init__(self, initial_balance, exchange_name, api_key, api_secret):
        self.initial_balance = float(initial_balance)
        self.portfolio = {
            'balance': self.initial_balance,
            'positions': {},
            'equity': self.initial_balance
        }
        self.exchange = self._connect_to_exchange(exchange_name, api_key, api_secret)
        self.strategy = TradingStrategy()
        self.trade_history = []

    def _connect_to_exchange(self, exchange_name, api_key, api_secret):
        exchange_class = getattr(ccxt, exchange_name.lower(), None)
        if not exchange_class:
            raise ValueError(f"صرافی {exchange_name} پشتیبانی نمی‌شود")
        
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True}
        })
        
        exchange.load_markets()
        return exchange

    def execute_auto_trade(self):
        try:
            symbol = 'BTC/USDT'
            df = self.get_market_data(symbol)
            signal = self.strategy.generate_signal(df)
            
            if signal['action'] == 'BUY':
                amount = self.calculate_position_size(signal['price'])
                if amount > 0:
                    self.execute_trade(symbol, 'buy', amount)
                    return f"خرید انجام شد: {amount:.6f} BTC"
            
            elif signal['action'] == 'SELL':
                if symbol in self.portfolio['positions']:
                    amount = min(self.portfolio['positions'][symbol], signal['amount'])
                    if amount > 0:
                        self.execute_trade(symbol, 'sell', amount)
                        return f"فروش انجام شد: {amount:.6f} BTC"
            
            return "سیگنال معاملاتی شناسایی نشد"
        
        except Exception as e:
            return f"خطا در معامله خودکار: {str(e)}"

    def calculate_position_size(self, entry_price, risk_percent=0.02, stop_loss_percent=0.05):
        risk_amount = self.portfolio['balance'] * risk_percent
        stop_loss_price = entry_price * (1 - stop_loss_percent)
        risk_per_unit = entry_price - stop_loss_price
        return (risk_amount / risk_per_unit)

    def execute_trade(self, symbol, side, amount):
        try:
            if side == 'buy':
                order = self.exchange.create_market_buy_order(symbol, amount)
            else:
                order = self.exchange.create_market_sell_order(symbol, amount)
            
            self._update_portfolio(order)
            self._record_trade(order, side)
            return True, "معامله با موفقیت انجام شد"
        except Exception as e:
            return False, f"خطا در اجرای معامله: {str(e)}"

    def _update_portfolio(self, order):
        symbol = order['symbol']
        side = order['side']
        amount = order['amount']
        cost = order['cost']
        
        if side == 'buy':
            self.portfolio['balance'] -= cost
            self.portfolio['positions'][symbol] = self.portfolio['positions'].get(symbol, 0) + amount
        else:
            self.portfolio['balance'] += cost
            self.portfolio['positions'][symbol] -= amount
            if self.portfolio['positions'][symbol] <= 0:
                del self.portfolio['positions'][symbol]
        
        self.portfolio['equity'] = self.portfolio['balance'] + sum(
            self.get_current_price(sym) * amt for sym, amt in self.portfolio['positions'].items()
        )

    def _record_trade(self, order, side):
        self.trade_history.append({
            'time': QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss'),
            'symbol': order['symbol'],
            'side': side,
            'amount': order['amount'],
            'price': order['price'],
            'value': order['cost']
        })

    def get_market_data(self, symbol='BTC/USDT', timeframe='1h', limit=100):
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    def get_current_price(self, symbol):
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker['last']

class TradingStrategy:
    def __init__(self):
        self.rsi_period = 14
        self.ma_period = 50
        self.rsi_oversold = 30
        self.rsi_overbought = 70

    def generate_signal(self, df):
        df['rsi'] = self._calculate_rsi(df['close'])
        df['ma'] = df['close'].rolling(self.ma_period).mean()
        
        last_row = df.iloc[-1]
        price = last_row['close']
        
        if last_row['rsi'] < self.rsi_oversold and last_row['close'] > last_row['ma']:
            return {'action': 'BUY', 'price': price, 'amount': 0.01}
        elif last_row['rsi'] > self.rsi_overbought and last_row['close'] < last_row['ma']:
            return {'action': 'SELL', 'price': price, 'amount': 0.01}
        else:
            return {'action': 'HOLD'}

    def _calculate_rsi(self, prices):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).ewm(span=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(span=self.rsi_period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('CryptoTraderPro', 'AutoTradingBot')
        self.trading_engine = None
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("ربات تریدر هوشمند")
        self.setGeometry(100, 100, 1200, 800)
        
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_setup_tab(), "تنظیمات اولیه")
        self.tabs.addTab(self.create_dashboard(), "داشبورد")
        self.tabs.addTab(self.create_trade_history_tab(), "تاریخچه معاملات")
        
        self.setCentralWidget(self.tabs)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.trading_timer = QTimer()
        self.trading_timer.timeout.connect(self.run_trading_cycle)

    def create_setup_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        group = QGroupBox("تنظیمات حساب کاربری")
        form = QFormLayout()
        
        self.balance_input = QDoubleSpinBox()
        self.balance_input.setRange(10, 1000000)
        self.balance_input.setSuffix(" USDT")
        
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(['binance', 'bybit', 'kucoin'])
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("کلید API")
        
        self.api_secret_input = QLineEdit()
        self.api_secret_input.setPlaceholderText("رمز API")
        
        form.addRow("موجودی اولیه:", self.balance_input)
        form.addRow("صرافی:", self.exchange_combo)
        form.addRow("کلید API:", self.api_key_input)
        form.addRow("رمز API:", self.api_secret_input)
        group.setLayout(form)
        
        self.start_btn = QPushButton("شروع تریدینگ خودکار")
        self.start_btn.clicked.connect(self.start_trading)
        
        layout.addWidget(group)
        layout.addStretch()
        layout.addWidget(self.start_btn)
        tab.setLayout(layout)
        return tab

    def create_dashboard(self):
        widget = QWidget()
        layout = QVBoxLayout()
        
        self.balance_label = QLabel("موجودی: 0.00 USDT")
        self.balance_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.equity_label = QLabel("ارزش پرتفوی: 0.00 USDT")
        
        self.positions_table = QTableWidget(5, 3)
        self.positions_table.setHorizontalHeaderLabels(["نماد", "مقدار", "ارزش"])
        
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)  # استفاده از QPainter
        
        layout.addWidget(self.balance_label)
        layout.addWidget(self.equity_label)
        layout.addWidget(QLabel("پوزیشن‌های باز:"))
        layout.addWidget(self.positions_table)
        layout.addWidget(QLabel("نمودار قیمت:"))
        layout.addWidget(self.chart_view)
        widget.setLayout(layout)
        return widget

    def create_trade_history_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        
        self.history_table = QTableWidget(10, 6)
        self.history_table.setHorizontalHeaderLabels(["زمان", "نماد", "نوع", "مقدار", "قیمت", "ارزش"])
        
        layout.addWidget(self.history_table)
        widget.setLayout(layout)
        return widget

    def start_trading(self):
        initial_balance = self.balance_input.value()
        exchange_name = self.exchange_combo.currentText()
        api_key = self.api_key_input.text()
        api_secret = self.api_secret_input.text()
        
        try:
            self.trading_engine = TradingEngine(initial_balance, exchange_name, api_key, api_secret)
            self.save_settings(initial_balance, exchange_name, api_key, api_secret)
            self.trading_timer.start(60000)  # هر 1 دقیقه
            self.update_ui()
            self.tabs.setCurrentIndex(1)
            QMessageBox.information(self, "موفقیت", "تریدینگ خودکار با موفقیت شروع شد")
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"خطا در شروع تریدینگ: {str(e)}")

    def run_trading_cycle(self):
        if self.trading_engine:
            result = self.trading_engine.execute_auto_trade()
            self.status_bar.showMessage(result, 5000)
            self.update_ui()

    def update_ui(self):
        if self.trading_engine:
            self.update_balance_info()
            self.update_positions_table()
            self.update_trade_history()
            self.update_price_chart()

    def update_balance_info(self):
        portfolio = self.trading_engine.portfolio
        self.balance_label.setText(f"موجودی: {portfolio['balance']:,.2f} USDT")
        self.equity_label.setText(f"ارزش پرتفوی: {portfolio['equity']:,.2f} USDT")

    def update_positions_table(self):
        positions = self.trading_engine.portfolio['positions']
        self.positions_table.setRowCount(len(positions))
        
        for row, (symbol, amount) in enumerate(positions.items()):
            price = self.trading_engine.get_current_price(symbol)
            value = amount * price
            
            self.positions_table.setItem(row, 0, QTableWidgetItem(symbol))
            self.positions_table.setItem(row, 1, QTableWidgetItem(f"{amount:.6f}"))
            self.positions_table.setItem(row, 2, QTableWidgetItem(f"{value:,.2f}"))

    def update_trade_history(self):
        history = self.trading_engine.trade_history[-10:]  # 10 معامله آخر
        self.history_table.setRowCount(len(history))
        
        for row, trade in enumerate(history):
            self.history_table.setItem(row, 0, QTableWidgetItem(trade['time']))
            self.history_table.setItem(row, 1, QTableWidgetItem(trade['symbol']))
            self.history_table.setItem(row, 2, QTableWidgetItem(trade['side']))
            self.history_table.setItem(row, 3, QTableWidgetItem(f"{trade['amount']:.6f}"))
            self.history_table.setItem(row, 4, QTableWidgetItem(f"{trade['price']:,.2f}"))
            self.history_table.setItem(row, 5, QTableWidgetItem(f"{trade['value']:,.2f}"))

    def update_price_chart(self):
        chart = QChart()
        chart.setTitle("نمودار قیمت BTC/USDT")
        
        series = QLineSeries()
        df = self.trading_engine.get_market_data()
        
        for i, price in enumerate(df['close']):
            series.append(i, price)
        
        chart.addSeries(series)
        chart.createDefaultAxes()
        self.chart_view.setChart(chart)

    def save_settings(self, balance, exchange, api_key, api_secret):
        self.settings.setValue('initial_balance', balance)
        self.settings.setValue('exchange', exchange)
        self.settings.setValue('api_key', api_key)
        self.settings.setValue('api_secret', api_secret)

    def load_settings(self):
        if self.settings.value('initial_balance'):
            self.balance_input.setValue(float(self.settings.value('initial_balance')))
        if self.settings.value('exchange'):
            self.exchange_combo.setCurrentText(self.settings.value('exchange'))
        if self.settings.value('api_key'):
            self.api_key_input.setText(self.settings.value('api_key'))
        if self.settings.value('api_secret'):
            self.api_secret_input.setText(self.settings.value('api_secret'))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    font = QFont()
    font.setFamily("Arial")
    app.setFont(font)
    
    window = TradingApp()
    window.show()
    sys.exit(app.exec_())