# rubyruby_client_render.py
import sys, os, json, requests
from PyQt5 import QtWidgets, QtCore
from websocket import WebSocketApp
import threading

SERVER = "https://rubyruby-server.onrender.com"
WS_SERVER = "wss://rubyruby-server.onrender.com/ws"
TOKEN_FILE = "user_token.json"

# ---------------- TOKEN ----------------
def load_token():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
                return data.get("username"), data.get("token")
        except:
            return None, None
    return None, None

def save_token(username, token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"username": username, "token": token}, f)

# ---------------- LOGIN DIALOG ----------------
class LoginDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rubyruby — Login / Registro")
        self.username = None
        layout = QtWidgets.QVBoxLayout(self)

        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        # Login
        tab_login = QtWidgets.QWidget()
        tabs.addTab(tab_login, "Login")
        lv = QtWidgets.QFormLayout(tab_login)
        self.login_user = QtWidgets.QLineEdit()
        self.login_pass = QtWidgets.QLineEdit()
        self.login_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        lv.addRow("Usuário", self.login_user)
        lv.addRow("Senha", self.login_pass)
        btn_login = QtWidgets.QPushButton("Entrar")
        btn_login.clicked.connect(self.do_login)
        lv.addRow(btn_login)

        # Registro
        tab_reg = QtWidgets.QWidget()
        tabs.addTab(tab_reg, "Registrar")
        rv = QtWidgets.QFormLayout(tab_reg)
        self.reg_user = QtWidgets.QLineEdit()
        self.reg_pass1 = QtWidgets.QLineEdit()
        self.reg_pass1.setEchoMode(QtWidgets.QLineEdit.Password)
        self.reg_pass2 = QtWidgets.QLineEdit()
        self.reg_pass2.setEchoMode(QtWidgets.QLineEdit.Password)
        rv.addRow("Usuário", self.reg_user)
        rv.addRow("Senha", self.reg_pass1)
        rv.addRow("Repita a senha", self.reg_pass2)
        btn_reg = QtWidgets.QPushButton("Registrar")
        btn_reg.clicked.connect(self.do_register)
        rv.addRow(btn_reg)

    def do_login(self):
        u = self.login_user.text().strip()
        p = self.login_pass.text().strip()
        if not u or not p: return
        try:
            r = requests.post(f"{SERVER}/login", json={"username": u, "password": p}).json()
            if r.get("ok"):
                self.username = u
                save_token(u, r.get("token"))
                self.accept()
            else:
                QtWidgets.QMessageBox.warning(self, "Erro", r.get("error",""))
        except:
            QtWidgets.QMessageBox.warning(self, "Erro", "Falha ao conectar com o servidor")

    def do_register(self):
        u = self.reg_user.text().strip()
        p1 = self.reg_pass1.text().strip()
        p2 = self.reg_pass2.text().strip()
        if p1 != p2:
            QtWidgets.QMessageBox.warning(self, "Erro", "Senhas não conferem")
            return
        try:
            r = requests.post(f"{SERVER}/register", json={"username": u, "password": p1}).json()
            if r.get("ok"):
                QtWidgets.QMessageBox.information(self, "OK", "Registrado com sucesso")
            else:
                QtWidgets.QMessageBox.warning(self, "Erro", r.get("error",""))
        except:
            QtWidgets.QMessageBox.warning(self, "Erro", "Falha ao conectar com o servidor")

# ---------------- WEBSOCKET ----------------
class WSClient(QtCore.QThread):
    message_received = QtCore.pyqtSignal(dict)

    def __init__(self, username):
        super().__init__()
        self.username = username
        self.ws = None

    def run(self):
        def on_message(ws, message):
            try:
                obj = json.loads(message)
                self.message_received.emit(obj)
            except:
                pass

        def on_open(ws):
            print("WebSocket conectado")

        def on_close(ws):
            print("WebSocket desconectado")

        self.ws = WebSocketApp(f"{WS_SERVER}/{self.username}",
                               on_message=on_message,
                               on_open=on_open,
                               on_close=on_close)
        self.ws.run_forever()

    def send(self, payload: dict):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                self.ws.send(json.dumps(payload))
            except:
                pass

# ---------------- CLIENT ----------------
class RubyrubyClient(QtWidgets.QMainWindow):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.current_target = None
        self.ws_thread = None
        self.setWindowTitle("Rubyruby — Cliente")
        self.resize(1000,600)
        self.setup_ui()
        self.start_ws()
        self.refresh_contacts()
        self.refresh_groups()

    def setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        h = QtWidgets.QHBoxLayout(central)

        # Left panel
        left = QtWidgets.QWidget()
        left.setFixedWidth(320)
        lv = QtWidgets.QVBoxLayout(left)
        self.lbl_user = QtWidgets.QLabel(f"Logado: {self.username}")
        self.lbl_user.setStyleSheet("font-weight:bold; color:#cc3366;")
        lv.addWidget(self.lbl_user)

        tabs = QtWidgets.QTabWidget()
        # Contatos
        tab_contacts = QtWidgets.QWidget()
        tc_layout = QtWidgets.QVBoxLayout(tab_contacts)
        self.list_contacts = QtWidgets.QListWidget()
        tc_layout.addWidget(self.list_contacts)
        btn_add = QtWidgets.QPushButton("Adicionar contato")
        btn_add.clicked.connect(self.add_contact)
        tc_layout.addWidget(btn_add)
        tabs.addTab(tab_contacts, "Contatos")
        # Grupos
        tab_groups = QtWidgets.QWidget()
        tg_layout = QtWidgets.QVBoxLayout(tab_groups)
        self.list_groups = QtWidgets.QListWidget()
        tg_layout.addWidget(self.list_groups)
        btn_create = QtWidgets.QPushButton("Criar grupo")
        btn_create.clicked.connect(self.create_group)
        btn_join = QtWidgets.QPushButton("Entrar em grupo")
        btn_join.clicked.connect(self.join_group)
        tg_layout.addWidget(btn_create)
        tg_layout.addWidget(btn_join)
        tabs.addTab(tab_groups, "Grupos")
        lv.addWidget(tabs)
        lv.addStretch()

        self.btn_theme = QtWidgets.QPushButton("Tema: Claro")
        self.btn_theme.setCheckable(True)
        self.btn_theme.toggled.connect(self.toggle_theme)
        lv.addWidget(self.btn_theme)
        h.addWidget(left)

        # Right panel
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        self.chat_title = QtWidgets.QLabel("Conversa")
        self.chat_title.setStyleSheet("font-weight:bold;")
        rv.addWidget(self.chat_title)
        self.chat_view = QtWidgets.QTextEdit()
        self.chat_view.setReadOnly(True)
        rv.addWidget(self.chat_view)
        send_layout = QtWidgets.QHBoxLayout()
        self.txt_message = QtWidgets.QLineEdit()
        send_layout.addWidget(self.txt_message)
        btn_send = QtWidgets.QPushButton("Enviar")
        btn_send.clicked.connect(self.send_message)
        send_layout.addWidget(btn_send)
        rv.addLayout(send_layout)
        h.addWidget(right)

        # Interações
        self.list_contacts.itemClicked.connect(self.open_contact)
        self.list_groups.itemClicked.connect(self.open_group)

    # ---------------- FUNÇÕES ----------------
    def start_ws(self):
        self.ws_thread = WSClient(self.username)
        self.ws_thread.message_received.connect(self.on_ws_message)
        self.ws_thread.start()

    def on_ws_message(self, obj):
        if obj.get("type")=="message":
            sender = obj.get("from")
            text = obj.get("text")
            tgt_type = obj.get("target_type")
            tgt = obj.get("to")
            cur = self.current_target
            if cur and cur.get("type")==tgt_type and str(cur.get("id"))==str(tgt):
                self.chat_view.append(f"[{sender}] {text}")

    # --- Contatos / Grupos ---
    def refresh_contacts(self):
        try:
            r = requests.get(f"{SERVER}/contacts/{self.username}").json()
            self.list_contacts.clear()
            for c in r.get("contacts", []):
                self.list_contacts.addItem(c)
        except: pass

    def refresh_groups(self):
        try:
            r = requests.get(f"{SERVER}/groups/{self.username}").json()
            self.list_groups.clear()
            for g in r.get("groups", []):
                it = QtWidgets.QListWidgetItem(f"{g['name']} (id:{g['id']})")
                it.setData(QtCore.Qt.UserRole, g)
                self.list_groups.addItem(it)
        except: pass

    def add_contact(self):
        text, ok = QtWidgets.QInputDialog.getText(self, "Adicionar Contato", "Usuário:")
        if ok and text:
            requests.post(f"{SERVER}/add_contact", json={"owner":self.username,"contact":text})
            self.refresh_contacts()

    def create_group(self):
        text, ok = QtWidgets.QInputDialog.getText(self, "Criar Grupo", "Nome do grupo:")
        if ok and text:
            requests.post(f"{SERVER}/create_group", json={"owner":self.username,"name":text})
            self.refresh_groups()

    def join_group(self):
        gid, ok = QtWidgets.QInputDialog.getInt(self, "Entrar em Grupo", "ID do grupo:")
        if ok:
            requests.post(f"{SERVER}/join_group", json={"user":self.username,"group_id":gid})
            self.refresh_groups()

    # --- Abrir conversa ---
    def open_contact(self, item):
        contact = item.text()
        self.current_target = {"type":"user","id":contact}
        self.chat_title.setText(f"Conversa com {contact}")
        try:
            r = requests.get(f"{SERVER}/messages/{self.username}/user/{contact}").json()
            self.chat_view.clear()
            for m in r.get("messages", []):
                self.chat_view.append(f"[{m['sender']}] {m['text']}")
        except: pass

    def open_group(self, item):
        g = item.data(QtCore.Qt.UserRole)
        self.current_target = {"type":"group","id":g['id']}
        self.chat_title.setText(f"Grupo: {g['name']}")
        try:
            r = requests.get(f"{SERVER}/messages/{self.username}/group/{g['id']}").json()
            self.chat_view.clear()
            for m in r.get("messages", []):
                self.chat_view.append(f"[{m['sender']}] {m['text']}")
        except: pass

    # --- Enviar mensagem ---
    def send_message(self):
        text = self.txt_message.text().strip()
        if not text or not self.current_target: return
        payload = {"type":"message","target_type":self.current_target["type"],"target":self.current_target["id"],"text":text}
        if self.ws_thread:
            self.ws_thread.send(payload)
        self.chat_view.append(f"[{self.username}] {text}")
        self.txt_message.clear()

    # --- Tema ---
    def toggle_theme(self, on):
        if on:
            self.setStyleSheet("QWidget {background:#222;color:#ddd} QPushButton{background:#444;color:#fff}")
            self.btn_theme.setText("Tema: Escuro")
        else:
            self.setStyleSheet("")
            self.btn_theme.setText("Tema: Claro")

# ---------------- MAIN ----------------
if __name__=="__main__":
    app = QtWidgets.QApplication(sys.argv)
    username, token = load_token()
    if not username:
        dlg = LoginDialog()
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            username = dlg.username
        else:
            sys.exit(0)
    w = RubyrubyClient(username)
    w.show()
    sys.exit(app.exec_())
