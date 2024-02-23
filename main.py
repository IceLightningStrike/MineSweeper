from base64 import b85encode

from time import sleep
from threading import Thread

import sys
import sqlite3

import numpy as np
from random import shuffle
from itertools import product

from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QPixmap, QIcon, QColor, QMouseEvent
from PyQt5.QtWidgets import QPushButton, QRadioButton, QButtonGroup, QAbstractItemView
from PyQt5.QtWidgets import QLabel, QInputDialog, QTableWidget, QTableWidgetItem, QErrorMessage


class Field:
    def __init__(self, width: int, height: int, mine_count: int) -> None:
        self.mine_count = mine_count
        self.width = width
        self.height = height

        self.array = [["[ ]"] * self.width for _ in range(self.height)]
        self.field = np.zeros(width * height).reshape(height, width)
        self.field[0] = np.ones(width)

        self.state = CONTINUE
        self.first_move_done = False

    def generate_field(self, line: int, column: int) -> None:
        if self.state != CONTINUE:
            return

        self.field = np.zeros(self.width * self.height).reshape(self.height, self.width)
        self.field[0] = np.ones(self.width)

        self.field = self.field.reshape(self.width * self.height)
        shuffle(self.field)
        self.field = self.field.reshape(self.height, self.width)

        while self.field[line][column] == 1 or self.calculate_count_of_mines_near_me(line, column) > 0:
            self.field = self.field.reshape(self.width * self.height)
            shuffle(self.field)
            self.field = self.field.reshape(self.height, self.width)

        self.field = self.field.reshape(self.height, self.width)

    def open_cell(self, line: int, column: int) -> None:
        if self.state != CONTINUE:
            return

        if self.array[line][column] != "[ ]":
            return

        if self.field[line][column] == 1:
            self.field[line][column] = 2
            self.state = LOSE
            return

        mines_count = self.calculate_count_of_mines_near_me(line, column)

        if mines_count:
            self.array[line][column] = f"[{mines_count}]"
        else:
            self.array[line][column] = f"   "
            self.ornate_cells_opening(line, column, set())

    def ornate_cells_opening(self, line: int, column: int, was: set) -> None:
        if self.state != CONTINUE:
            return

        if (line, column) in was:
            return

        was.add((line, column))

        if self.array[line][column] in ["[?]", "[F]"]:
            return

        mines_count = self.calculate_count_of_mines_near_me(line, column)
        if mines_count:
            self.array[line][column] = f"[{mines_count}]"
            return

        self.array[line][column] = f"   "
        for new_line, new_column in product([-1, 0, 1], [-1, 0, 1]):
            if not ((0 <= line + new_line < self.height) and (0 <= column + new_column < self.width)):
                continue
            self.ornate_cells_opening(line + new_line, column + new_column, was)

    def change_with_flag(self, line: int, column: int) -> None:
        if self.state != CONTINUE:
            return

        if (0 <= line < self.height) and (0 <= column < self.width):
            if self.array[line][column] == "[ ]":
                self.array[line][column] = "[F]"
            elif self.array[line][column] == "[F]":
                self.array[line][column] = "[ ]"

    def change_with_mark(self, line: int, column: int) -> None:
        if self.state != CONTINUE:
            return

        if (0 <= line < self.height) and (0 <= column < self.width):
            if self.array[line][column] == "[ ]":
                self.array[line][column] = "[?]"
            elif self.array[line][column] == "[?]":
                self.array[line][column] = "[ ]"

    def clear_cell(self, line: int, column: int) -> None:
        if 0 <= line < self.height and 0 <= column < self.width:
            self.array[line][column] = "[ ]"

    def update_state(self) -> None:
        if self.state != CONTINUE:
            return

        for i, line in enumerate(self.field):
            for j, symbol in enumerate(line):
                if symbol == 1 and self.array[i][j] != "[F]" or symbol != 1 and self.array[i][j] == "[F]":
                    self.state = CONTINUE
                    return
                if symbol == 0 and self.array[i][j] in ["[ ]", "[?]", "[F]"]:
                    self.state = CONTINUE
                    return
        else:
            self.state = WIN

    def calculate_count_of_mines_near_me(self, line: int, column: int) -> int:
        count = 0

        for i, j in product([-1, 0, 1], [-1, 0, 1]):
            if (0 <= line + i < self.height) and (0 <= column + j < self.width):
                count += (self.field[line + i][column + j] == 1) * (i != 0 or j != 0)

        return count


class Sapper(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setGeometry(500, 250, 550, 675)
        self.setFixedSize(1100, 675)
        self.setWindowIcon(QIcon('pictures\\icon.png'))
        self.setWindowTitle('Сапёр на минималках')
        self.setMouseTracking(True)

        self.game_field = Field(10, 10, 10)
        self.current_move = OPEN

        self.user_name, ok_pressed = QInputDialog.getText(self, "Введите ник", "Как нам вас называть?")

        if not ok_pressed:
            make_error("Перезапустите программу, для корректной работы!")

        if check_user_in_db(self.user_name):
            user_password, ok_pressed = QInputDialog.getText(self, " ", f"Введите пароль от {self.user_name}")
            if not check_user_password_in_db(self.user_name, user_password):
                make_error(f"Неверный пароль для {self.user_name}")
        else:
            user_password, ok_pressed = QInputDialog.getText(self, " ", f"Придумайте пароль для {self.user_name}")
            if not ok_pressed:
                make_error("Перезапустите программу, для корректной работы!")
            set_user_and_password_in_db(self.user_name, user_password)

        self.state_text = QLabel("Игра не начата!", self)
        self.state_text.setGeometry(575, 15, 500, 30)
        self.state_text.setAlignment(Qt.AlignCenter)

        self.restart_button = QPushButton("Новая игра", self)
        self.restart_button.clicked.connect(self.new_game_option)
        self.restart_button.setGeometry(575, 45, 500, 30)

        self.stop_game_button = QPushButton("Остановить игру", self)
        self.stop_game_button.clicked.connect(self.stop_game_option)
        self.stop_game_button.setGeometry(575, 75, 500, 30)
        self.stop_game_button.setEnabled(False)

        self.continue_game = QPushButton("Продолжить игру", self)
        self.continue_game.clicked.connect(self.continue_game_option)
        self.continue_game.setGeometry(575, 105, 500, 30)
        self.continue_game.setEnabled(False)

        self.time_displaying = QLabel("0.0 секунд", self)
        self.time_displaying.setGeometry(25, 105, 500, 30)
        self.time_displaying.setAlignment(Qt.AlignCenter)

        self.game_time = 0
        self.time_calculating_is_active = True

        self.time_thread = Thread(target=self.time_control)
        self.time_thread.start()

        self.second_timer = QTimer()
        self.second_timer.timeout.connect(self.update_leaderboard)
        self.second_timer.start(10)

        self.empty_icon = QIcon("pictures\\empty.png")
        self.opened_icon = QIcon("pictures\\opened.png")
        self.flag_icon = QIcon("pictures\\flag.png")
        self.bomb_icon = QIcon("pictures\\bomb.png")
        self.activated_bomb_icon = QIcon("pictures\\activated_bomb.png")
        self.question_mark_icon = QIcon("pictures\\interrogative.png")
        self.from_one_to_eight_icon = [QIcon(f"pictures\\{n}.png") for n in range(1, 9)]

        flag_pixmap = QPixmap("pictures\\flag.png")
        push_button_flag = QRadioButton(self)
        push_button_flag.setGeometry(137, 70, 50, 50)
        push_button_flag.clicked.connect(self.change_flag)

        mine_pixmap = QPixmap("pictures\\interrogative.png")
        push_button_idk = QRadioButton(self)
        push_button_idk.setGeometry(275, 70, 50, 50)
        push_button_idk.clicked.connect(self.change_flag)

        shovel_pixmap = QPixmap("pictures\\shovel.png")
        push_button_open = QRadioButton(self)
        push_button_open.setGeometry(412, 70, 50, 50)
        push_button_open.clicked.connect(self.change_flag)
        push_button_open.setChecked(True)

        for index, pixmap in enumerate([flag_pixmap, mine_pixmap, shovel_pixmap]):
            image = QLabel(self)
            image.move((index + 1) * 137 - 15, 25)
            image.setPixmap(pixmap.scaledToWidth(50).scaledToHeight(50))

        self.upper_button_group = QButtonGroup()
        self.upper_button_group.addButton(push_button_flag, id=1)
        self.upper_button_group.addButton(push_button_idk, id=2)
        self.upper_button_group.addButton(push_button_open, id=3)

        self.mouse_coordinates = [0, 0]
        self.buttons = []

        for x in range(10):
            self.buttons.append([])
            for y in range(10):
                button = QPushButton(self)
                button.setIcon(self.empty_icon)
                button.setIconSize(QSize(50, 50))
                button.setGeometry(25 + x * 50, 150 + y * 50, 50, 50)
                button.clicked.connect(self.move_with_cell)
                button.setMouseTracking(True)
                button.setEnabled(False)

                self.buttons[-1].append(button)

        old_data = sorted(map(lambda array: array[1:], get_all_db()), key=sorting_rule)

        self.tableWidget = QTableWidget(len(old_data), 2, self)
        self.tableWidget.setHorizontalHeaderLabels(['Nick', 'Record'])
        self.tableWidget.horizontalHeader().setDefaultSectionSize(240)
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tableWidget.setGeometry(575, 150, 501, 500)

        self.update_leaderboard()

    def update_leaderboard(self) -> None:
        data = sorted(map(lambda array: array[1:], get_all_db()), key=sorting_rule)

        for index, line in enumerate(data):
            arr = [QTableWidgetItem(line[0]), QTableWidgetItem(str(round(float(line[-1]), 1)))]

            if float(line[-1]) == -1:
                arr = [QTableWidgetItem(line[0]), QTableWidgetItem("-")]

            for other_index, elem in enumerate(arr):
                elem.setTextAlignment(Qt.AlignCenter)
                self.tableWidget.setItem(index, other_index, elem)

        try:
            self.tableWidget.item(0, 0).setBackground(QColor(255, 215, 0))
            self.tableWidget.item(0, 1).setBackground(QColor(255, 215, 0))
        except AttributeError:
            pass

        try:
            self.tableWidget.item(1, 0).setBackground(QColor(192, 192, 192))
            self.tableWidget.item(1, 1).setBackground(QColor(192, 192, 192))
        except AttributeError:
            pass

        try:
            self.tableWidget.item(2, 0).setBackground(QColor(205, 127, 50))
            self.tableWidget.item(2, 1).setBackground(QColor(205, 127, 50))
        except AttributeError:
            pass

        for index in range(self.tableWidget.rowCount()):
            name, record = self.tableWidget.item(index, 0), self.tableWidget.item(index, 1)

            if name.text() == self.user_name:
                record = str(round(getting_record_by_name(self.user_name), 1))
                new_item = QTableWidgetItem()

                if float(record) == -1:
                    record = "-"

                self.tableWidget.setItem(index, 1, new_item)
                self.tableWidget.item(index, 1).setText(str(record))
                self.tableWidget.item(index, 0).setBackground(QColor(168, 228, 160))
                self.tableWidget.item(index, 1).setBackground(QColor(168, 228, 160))
                self.tableWidget.item(index, 0).setTextAlignment(Qt.AlignCenter)
                self.tableWidget.item(index, 1).setTextAlignment(Qt.AlignCenter)

                break

    def new_game_option(self) -> None:
        self.state_text.setText("Игра продолжается!")
        self.game_time = 0

        del self.game_field
        self.game_field = Field(10, 10, 10)
        self.current_move = OPEN

        self.change_flag()

        for line in self.buttons:
            for button in line:
                button.setIcon(self.empty_icon)
                button.setEnabled(True)

        self.stop_game_button.setEnabled(True)
        self.continue_game.setEnabled(False)

    def stop_game_option(self) -> None:
        self.state_text.setText("Игра приостановлена")

        for line in self.buttons:
            for button in line:
                button.setEnabled(False)

        self.stop_game_button.setEnabled(False)
        self.continue_game.setEnabled(True)

    def continue_game_option(self) -> None:
        self.state_text.setText("Игра продолжается!")

        for line in self.buttons:
            for button in line:
                button.setEnabled(True)

        self.stop_game_button.setEnabled(True)
        self.continue_game.setEnabled(False)

    def time_control(self) -> None:
        while self.time_calculating_is_active:
            self.update()
            sleep(0.1)

            if self.stop_game_button.isEnabled() and self.game_field.state == CONTINUE:
                self.game_time += 0.1
                self.time_displaying.setText(f"{self.game_time:.1f} секунд")

            if self.game_field.state == WIN:
                recalculating_record(self.user_name, self.game_time)

    def change_flag(self) -> None:
        for index, button in enumerate(self.upper_button_group.buttons()):
            if button.isChecked():
                match index:
                    case 0:
                        self.current_move = FLAG
                    case 1:
                        self.current_move = QUESTION
                    case 2:
                        self.current_move = OPEN

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.mouse_coordinates = [event.x(), event.y()]

    def closeEvent(self, event):
        self.time_calculating_is_active = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.stop_game_button.isEnabled():
            return

        if event.buttons() == Qt.RightButton:
            if 25 < self.mouse_coordinates[0] < 525 and 150 < self.mouse_coordinates[1] < 650:
                x, y = int(self.mouse_coordinates[0] - 25), int(self.mouse_coordinates[1] - 150)
                self.game_field.change_with_flag(y // 50 - (y % 50 == 0 and y), x // 50 - (x % 50 == 0 and x))
                self.game_field.update_state()
                self.redrawing_field()

    def move_with_cell(self) -> None:
        sender = self.sender()
        for index, elem in enumerate(self.buttons):
            if sender in elem:
                line, column = elem.index(sender), index

                if self.current_move == FLAG:
                    self.game_field.change_with_flag(line, column)
                elif self.current_move == QUESTION:
                    self.game_field.change_with_mark(line, column)
                else:
                    if not self.game_field.first_move_done:
                        self.game_field.first_move_done = True
                        self.game_field.generate_field(line, column)

                    self.game_field.open_cell(line, column)

                break

        self.redrawing_field()

    def redrawing_field(self) -> None:
        self.game_field.update_state()

        if self.game_field.state == WIN:
            self.state_text.setText("Вы выиграли =)")
            self.stop_game_button.setEnabled(False)
            self.continue_game.setEnabled(False)
        elif self.game_field.state == LOSE:
            self.state_text.setText("Вы проиграли =(")
            self.stop_game_button.setEnabled(False)
            self.continue_game.setEnabled(False)
        else:
            self.state_text.setText("Игра продолжается!")

        for index_i, elem_i in enumerate(self.buttons):
            for index_j, cur_button in enumerate(elem_i):
                element = self.game_field.array[index_j][index_i]
                cur_button: QPushButton

                if self.game_field.state == LOSE:
                    if self.game_field.field[index_j][index_i] == 1:
                        cur_button.setIcon(self.bomb_icon)
                    if self.game_field.field[index_j][index_i] == 2:
                        cur_button.setIcon(self.activated_bomb_icon)
                else:
                    if element == "[ ]":
                        cur_button.setIcon(self.empty_icon)
                    elif element == "   ":
                        cur_button.setIcon(self.opened_icon)
                    elif element == "[F]":
                        cur_button.setIcon(self.flag_icon)
                    elif element == "[?]":
                        cur_button.setIcon(self.question_mark_icon)
                    elif element.lstrip("[").rstrip("]").isdigit():
                        cur_button.setIcon(self.from_one_to_eight_icon[int(element[1]) - 1])


def sorting_rule(array: list) -> list[float, str]:
    return [float("inf") if float(array[-1]) == -1 else float(array[-1]), array[0]]


def except_hook(cls, exception, traceback):
    sys.__excepthook__(cls, exception, traceback)


def make_error(message: str) -> None:
    error_dialog = QErrorMessage()
    error_dialog.showMessage(message)
    app.exec_()
    raise SystemExit


def get_connection() -> sqlite3.connect:
    connection = sqlite3.connect('Records.db')
    cursor = connection.cursor()

    cursor.execute("PRAGMA key='Yandex'")
    connection.commit()

    return connection


def init_database() -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("PRAGMA key='Yandex';")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            ID INTEGER PRIMARY KEY,
            UserName TEXT,
            Time TEXT
        )"""
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS passwords (
            ID INTEGER PRIMARY KEY,
            Password TEXT
        )"""
    )

    connection.commit()
    connection.close()


def get_all_db() -> list:
    connection = get_connection()
    cursor = connection.cursor()

    arr = list(cursor.execute("SELECT * FROM results"))
    connection.close()

    return arr


def recalculating_record(user_name: str, imaginary_record: float) -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(f"SELECT Time FROM results WHERE UserName = '{user_name}'")
    connection.commit()

    real_record = float(cursor.fetchone()[0])

    if real_record == -1:
        cursor.execute(f"UPDATE results SET Time = '{imaginary_record}' WHERE UserName = '{user_name}'")
        connection.commit()
    elif imaginary_record < real_record:
        cursor.execute(f"UPDATE results SET Time = '{imaginary_record}' WHERE UserName = '{user_name}'")
        connection.commit()

    connection.close()


def getting_record_by_name(user_name: str) -> float:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(f"SELECT Time FROM results WHERE UserName = '{user_name}'")

    answer = float(cursor.fetchone()[0])
    connection.close()

    return answer


def check_user_in_db(user_name: str) -> bool:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(f"SELECT * FROM results WHERE UserName = '{user_name}';")

    answer = bool(cursor.fetchone())
    connection.close()

    return answer


def check_user_password_in_db(user_name: str, user_password: str) -> bool:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(f"""SELECT Password FROM passwords
                        WHERE ID=(SELECT ID FROM results WHERE UserName = '{user_name}')""")

    answer = (b85encode(user_password.encode("UTF-8")),) == cursor.fetchone()
    connection.close()

    return answer


def set_user_and_password_in_db(user_name: str, user_password: str) -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("INSERT INTO results (UserName, Time) VALUES(?, ?)", (user_name, -1))
    connection.commit()

    cursor.execute("INSERT INTO passwords (Password) VALUES(?)", (b85encode(user_password.encode("UTF-8")),))
    connection.commit()

    connection.close()


FLAG, QUESTION, OPEN = -4, -3, -2
LOSE, CONTINUE, WIN = -1, 0, 1
CONTINUES, STOPPED = 2, 3

if __name__ == '__main__':
    init_database()

    app = QApplication(sys.argv)
    sapper_window = Sapper()
    sapper_window.show()

    sys.__excepthook__ = except_hook
    sys.exit(app.exec_())
