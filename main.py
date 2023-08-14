from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QTableWidgetItem, QPushButton

from binance.client import Client
from binance import ThreadedWebsocketManager
from config import BINANCE_API_KEY, BINANCE_API_SECRET
import datetime

import sys
import os


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), "main.ui"), self)
        self.setWindowTitle("Main")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.binance_client = Client(
            api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET
        )
        self.twm = ThreadedWebsocketManager(
            api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET
        )
        self.twm.daemon = True
        self.twm.start()
        self.binance_user_socket = self.twm.start_futures_user_socket(
            callback=self.user_message
        )
        self.orders = self.binance_client.futures_get_open_orders()
        self.positions = list(filter(
            lambda x: float(x['entryPrice']) != 0,
            self.binance_client.futures_position_information()
        ))
        print("ALREADY OPEN ORDERS:", self.orders)
        print("ALREADY OPEN POSITIONS:", self.positions)

        def cancel_all_orders(logicalIndex):
            if logicalIndex == 0:
                symbols = list(set(map(lambda x: x["symbol"], self.orders)))
                for symbol in symbols:
                    self.binance_client.futures_cancel_all_open_orders(
                        symbol=symbol
                    )
        self.orders_tbl.horizontalHeader().sectionClicked.connect(
            cancel_all_orders
        )

        self.need_to_update_orders = True
        self.need_to_update_positions = True

        fps = 60
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_tables)
        self.timer.start(int(1000 / fps))

    def update_tables(self):
        if self.need_to_update_orders:
            self.update_orders()
        if self.need_to_update_positions:
            self.update_positions()

    def user_message(self, msg):
        print(msg)
        if msg['e'] == 'ORDER_TRADE_UPDATE':
            order = {
                'orderId': msg['o']['i'],
                'symbol': msg['o']['s'],
                'status': msg['o']['X'],
                'clientOrderId': msg['o']['c'],
                'price': msg['o']['p'],
                'avgPrice': msg['o']['ap'],
                'origQty': msg['o']['q'],
                'executedQty': msg['o']['z'],
                # cumQuote
                'timeInForce': msg['o']['f'],
                'type': msg['o']['o'],
                'reduceOnly': msg['o']['R'],
                'closePosition': msg['o']['cp'],
                'side': msg['o']['S'],
                'positionSide': msg['o']['ps'],
                'stopPrice': msg['o']['sp'],
                'workingType': msg['o']['wt'],
                'priceProtect': msg['o']['pP'],
                'origType': msg['o']['ot'],
                'time': msg['o']['T'],
                'updateTime': msg['T'],
            }
            self.orders = list(filter(
                lambda x: x["orderId"] != order["orderId"],
                self.orders
            )) + [order]
            self.orders = list(filter(
                lambda x: x["status"] not in ("CANCELED", "FILLED"),
                self.orders
            ))
            self.need_to_update_orders = True

        elif msg['e'] == 'ACCOUNT_UPDATE':
            for ps in msg['a']['P']:
                position = {
                    'symbol': ps['s'],
                    'positionAmt': ps['pa'],
                    'entryPrice': ps['ep'],
                    'unRealizedProfit': ps['up'],
                    'marginType': ps['mt'],
                    'isolatedWallet': ps['iw'],
                    'positionSide': ps['ps'],
                }

                if self.positions == []:
                    self.positions.append(position)

                elif float(position['positionAmt']) == 0:
                    for ops in self.positions:
                        if all([
                            ops['symbol'] == position['symbol'],
                            ops['positionSide'] == position['positionSide'],
                            ops['marginType'] == position['marginType']
                        ]):
                            self.positions.remove(ops)
                else:
                    for ops in self.positions:
                        if all([
                            ops['symbol'] == position['symbol'],
                            ops['positionSide'] == position['positionSide'],
                            ops['marginType'] == position['marginType']
                        ]):
                            self.positions.remove(ops)
                            self.positions.append(position)
                        else:
                            self.positions.append(position)
            self.need_to_update_positions = True

    def update_orders(self):
        # self.orders_tbl.clearContents()
        self.orders_tbl.setRowCount(0)
        for i, order in enumerate(self.orders):
            self.orders_tbl.insertRow(i)

            self.orders_tbl.setItem(i, 0, QTableWidgetItem())
            btn = QPushButton("Cancel")
            btn.clicked.connect(
                lambda: self.binance_client.futures_cancel_order(
                    symbol=order["symbol"],
                    orderId=order["orderId"],
                )
            )
            self.orders_tbl.setCellWidget(i, 0, btn)

            dt = datetime.datetime.fromtimestamp(order["time"] / 1000)
            dt = dt.isoformat(sep=" ", timespec="milliseconds")
            self.orders_tbl.setItem(i, 1, QTableWidgetItem(dt))
            self.orders_tbl.setItem(i, 2, QTableWidgetItem(order["symbol"]))
            self.orders_tbl.setItem(i, 3, QTableWidgetItem(order["type"]))
            self.orders_tbl.setItem(i, 4, QTableWidgetItem(order["positionSide"])) # noqa
            self.orders_tbl.setItem(i, 5, QTableWidgetItem(order["side"]))
            self.orders_tbl.setItem(i, 6, QTableWidgetItem(order["price"]))
            self.orders_tbl.setItem(i, 7, QTableWidgetItem(order["status"]))
            ro = str(order["reduceOnly"])
            self.orders_tbl.setItem(i, 8, QTableWidgetItem(ro))

        self.need_to_update_orders = False

    def update_positions(self):
        # self.positions_tbl.clearContents()
        self.positions_tbl.setRowCount(0)
        for i, position in enumerate(self.positions):
            self.positions_tbl.insertRow(i)

            self.positions_tbl.setItem(i, 0, QTableWidgetItem())
            btn = QPushButton("Market")
            btn.clicked.connect(
                lambda: self.binance_client.futures_create_order(
                    symbol=position["symbol"],
                    side="SELL" if position["positionSide"] == "LONG" else "BUY", # noqa
                    type="MARKET",
                    positionSide=position["positionSide"],
                    quantity=position["positionAmt"] if position["positionSide"] == "LONG" else position["positionAmt"][1:], # noqa
                )
            )
            self.positions_tbl.setCellWidget(i, 0, btn)
            self.positions_tbl.setItem(i, 1, QTableWidgetItem(position["symbol"])) # noqa
            self.positions_tbl.setItem(i, 2, QTableWidgetItem(
                position["positionAmt"] if position["positionSide"] == "LONG" else position["positionAmt"][1:] # noqa
            ))
            self.positions_tbl.setItem(i, 3, QTableWidgetItem(
                str(abs(float(position["positionAmt"])) * float(position["entryPrice"])) # noqa
            ))
            self.positions_tbl.setItem(i, 4, QTableWidgetItem(position["entryPrice"])) # noqa
            self.positions_tbl.setItem(i, 5, QTableWidgetItem(position["marginType"])) # noqa
            self.positions_tbl.setItem(i, 6, QTableWidgetItem(position["isolatedWallet"])) # noqa

        self.need_to_update_positions = False


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec_()
