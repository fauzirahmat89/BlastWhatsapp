
import sys
import time
import urllib.parse
import os
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFileDialog, QTableView, QTextEdit, 
                             QLineEdit, QSpinBox, QProgressBar, QMessageBox, QDialog, 
                             QFormLayout, QGroupBox, QSplitter, QComboBox, QCheckBox)
from PyQt6.QtCore import Qt, QAbstractTableModel, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QFont

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager

# --- Models ---

class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super(PandasModel, self).__init__()
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._data.columns[col]
        return None

# --- Worker Thread for Automation ---

class SenderWorker(QThread):
    progress = pyqtSignal(int, str) # progress value, log message
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, df, message_template, image_path, delay, max_messages, user_data_dir, profile_dir):
        super().__init__()
        self.df = df
        self.message_template = message_template
        self.image_path = image_path
        self.delay = delay
        self.max_messages = max_messages
        self.user_data_dir = user_data_dir
        self.profile_dir = profile_dir # In Firefox logic, we just combine these or use the full path
        self.is_running = True

    def run(self):
        driver = None
        try:
            self.progress.emit(0, "Initializing Firefox Driver...")
            
            options = Options()
            
            # Handle Profile
            # If user selected a specific profile folder, we use it.
            # user_data_dir is usually ~/.mozilla/firefox
            # profile_dir is the specific folder (e.g. xxxxx.default)
            if self.user_data_dir and self.profile_dir:
                full_profile_path = os.path.join(self.user_data_dir, self.profile_dir)
                if os.path.exists(full_profile_path):
                    self.progress.emit(2, f"Using profile: {self.profile_dir}")
                    options.add_argument("-profile")
                    options.add_argument(full_profile_path)
            
            service = Service(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=options)
            
            self.progress.emit(5, "Opening WhatsApp Web...")
            driver.get("https://web.whatsapp.com")
            
            self.progress.emit(10, "Please scan QR code if not logged in. Waiting for 30s...")
            try:
                # Wait for main element to ensure login
                WebDriverWait(driver, 60).until(
                    EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
                )
                self.progress.emit(15, "Logged in successfully!")
            except:
                self.progress.emit(15, "Login wait timed out. Attempting to proceed (Manual check needed if QR still there).")

            total_messages = min(len(self.df), self.max_messages)
            
            for index, row in self.df.iterrows():
                if not self.is_running:
                    break
                
                if index >= self.max_messages:
                    self.progress.emit(100, f"Reached limit of {self.max_messages} messages.")
                    break

                phone = str(row.get('Phone', '')).strip()
                if not phone:
                    self.progress.emit(int((index/total_messages)*100), f"Skipping row {index+1}: No Phone number")
                    continue
                
                # Format message
                try:
                    # Simple template replacement
                    msg = self.message_template
                    for col in self.df.columns:
                        val = str(row[col])
                        msg = msg.replace(f"{{{col}}}", val)
                except Exception as e:
                    self.progress.emit(int((index/total_messages)*100), f"Error formatting message for {phone}: {e}")
                    continue

                self.progress.emit(int((index/total_messages)*100), f"Sending to {phone}...")
                
                try:
                    # 1. Open Chat
                    encoded_msg = urllib.parse.quote(msg)
                    link = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"
                    driver.get(link)
                    
                    # Wait for chat to load (input box available)
                    input_box_xpath = '//div[@contenteditable="true"][@data-tab="10"]'
                    try:
                        WebDriverWait(driver, 20).until(
                            EC.presence_of_element_located((By.XPATH, input_box_xpath))
                        )
                    except:
                        self.progress.emit(int((index/total_messages)*100), f"Failed to load chat for {phone}. Number might be invalid.")
                        continue

                    # 2. Attach Image if exists
                    if self.image_path and os.path.exists(self.image_path):
                        try:
                            # Click attach button (New: Plus icon, Old: Clip icon)
                            attach_xpath = '//span[@data-icon="plus-rounded"] | //div[@title="Attach"] | //span[@data-icon="clip"]'
                            attach_btn = WebDriverWait(driver, 15).until(
                                EC.presence_of_element_located((By.XPATH, attach_xpath))
                            )
                            # Wait a bit for UI to settle (to avoid menu closing immediately if still loading)
                            time.sleep(1)
                            
                            # Use JavaScript Click for Attach button to avoid interception
                            driver.execute_script("arguments[0].click();", attach_btn)
                            
                            time.sleep(2) # Wait for menu animation
                            
                            # Explicitly CLICK "Photos & Videos" button
                            print("Clicking 'Photos & Videos' button...")
                            try:
                                # Updated Robust XPaths based on HTML analysis
                                photo_video_xpath = (
                                    '//*[contains(text(), "Foto & Video")] | '         
                                    '//*[contains(text(), "Photos & Videos")] | '
                                    '//*[local-name()="svg"]/*[local-name()="title"][text()="ic-filter-filled"]/ancestor::div[@role="button"] | '
                                    '//*[local-name()="svg"]/*[local-name()="title"][text()="ic-filter-filled"]/ancestor::li'
                                )
                                
                                # Wait for elements
                                buttons = WebDriverWait(driver, 5).until(
                                    EC.presence_of_all_elements_located((By.XPATH, photo_video_xpath))
                                )
                                
                                target_btn = None
                                for btn in buttons:
                                    # Safety Check: ensure we don't click Sticker
                                    # Get outer HTML to check for "Sticker" keyword nearby
                                    try:
                                        # Go up a few levels to check context
                                        context_html = btn.find_element(By.XPATH, "./../..").get_attribute('outerHTML')
                                        if "Stiker" in context_html or "Sticker" in context_html or "wds-ic-sticker" in context_html:
                                            continue
                                    except:
                                        pass
                                        
                                    target_btn = btn
                                    break
                                
                                if target_btn:
                                    print("Found Photo/Video button via text/icon match.")
                                    driver.execute_script("arguments[0].click();", target_btn)
                                else:
                                    # Fallback: Just click the 2nd item in the list (index 1) if strictly safe
                                    print("Text/Icon match suspect. Trying fallback to 2nd list item...")
                                    fallback_xpath = '//ul/li[2]//div[@role="button"]'
                                    fallback_btn = driver.find_element(By.XPATH, fallback_xpath)
                                    driver.execute_script("arguments[0].click();", fallback_btn)

                                time.sleep(2) # Wait for input spawn
                                
                            except Exception as e:
                                print(f"Failed to click Photo/Video button: {e}")
                                # DEBUG: Dump the menu HTML to see what's wrong
                                try:
                                    menu = driver.find_element(By.XPATH, '//ul')
                                    print("--- DUMPING MENU HTML FOR DEBUGGING ---")
                                    print(menu.get_attribute('outerHTML')[:500]) # Print first 500 chars
                                    print("--- END DUMP ---")
                                except:
                                    print("Could not dump menu HTML.")
                                # raise e # Do not raise, let it try to find input anyway

                            # Find the file input that accepts VIDEO (identifies Photo/Video input)
                            inputs = driver.find_elements(By.XPATH, '//input[@type="file"]')
                            target_input = None
                            
                            for inp in inputs:
                                accept = inp.get_attribute('accept')
                                if accept and 'video' in accept:
                                    target_input = inp
                                    break
                            
                            # Fallback: Just take the last input spawned
                            if not target_input and inputs:
                                target_input = inputs[-1]
                            
                            if target_input:
                                target_input.send_keys(self.image_path)
                            else:
                                raise Exception("No file input found after clicking Photos & Videos.")
                            
                            # Wait for preview and send button (Image/Doc)
                            
                            # Wait for preview and send button (Image/Doc)
                            # CRITICAL: Wait for the image/doc to actually load in the preview modal
                            
                            # Multiple selectors for the Send button in the preview modal
                            # 1. Standard icon spans
                            # 2. The green circle button wrapper (usually has aria-label="Send" or "Kirim")
                            # 3. The specific class provided by user (risky if dynamic, but added as fallback)
                            
                            send_xpath = (
                                '//span[@data-icon="send"] | '
                                '//span[@data-icon="wds-ic-send-filled"] | '
                                '//span[@data-icon="send-light"] | '
                                '//div[@aria-label="Send"] | '
                                '//div[@aria-label="Kirim"] | '
                                '//div[contains(@class, "x1ey2m1c") and @role="button"]' # Adjusted to look for button role
                            )
                            
                            # Increased wait time and specific condition
                            send_btn_img = WebDriverWait(driver, 15).until(
                                EC.presence_of_element_located((By.XPATH, send_xpath))
                            )
                            
                            # Force wait for animation/overlay to clear
                            time.sleep(2) 
                            
                            # Use JavaScript Click for Image Send
                            driver.execute_script("arguments[0].click();", send_btn_img)
                            
                            # Wait for upload and return to chat
                            time.sleep(3)
                            
                        except Exception as e:
                             self.progress.emit(int((index/total_messages)*100), f"Error sending image to {phone}: {e}")
                    
                    # 3. Send Text Message
                    # The text is likely still in the input box from the initial URL load.
                    # We try to find the send button again (now in main chat view) and click it.
                    try:
                        self.progress.emit(int((index/total_messages)*100), f"Sending text to {phone}...")
                        
                        send_xpath = '//span[@data-icon="send"] | //span[@data-icon="wds-ic-send-filled"] | //span[@data-icon="send-light"] | //button[@aria-label="Send"]'
                        # Reduced timeout as button should be there if text is present
                        send_btn = WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable((By.XPATH, send_xpath))
                        )
                        driver.execute_script("arguments[0].click();", send_btn)
                    except:
                        # Fallback: Press Enter on the active element (the input box)
                        # self.progress.emit(int((index/total_messages)*100), f"Click failed, trying ENTER key for {phone}...")
                        try:
                             driver.switch_to.active_element.send_keys(Keys.ENTER)
                        except Exception as ex:
                             self.progress.emit(int((index/total_messages)*100), f"Failed to send text to {phone}: {ex}")
                    
                    self.progress.emit(int(((index+1)/total_messages)*100), f"Sent to {phone}")
                    
                    time.sleep(self.delay)

                except Exception as e:
                    self.progress.emit(int((index/total_messages)*100), f"Failed to send to {phone}: {e}")

            self.progress.emit(100, "Automation Complete!")
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if driver:
                time.sleep(5)
                # driver.quit() # Uncomment to auto-close
                self.finished.emit()

    def stop(self):
        self.is_running = False

# --- Dialogs ---

class EnvDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Environment Setup (Firefox)")
        self.resize(500, 200)
        self.setModal(True)
        self.layout = QFormLayout(self)
        
        # Temp Session Checkbox
        self.temp_session_cb = QCheckBox("Use Temporary Session (Requires QR Scan every time)")
        self.temp_session_cb.toggled.connect(self.toggle_inputs)
        self.layout.addRow(self.temp_session_cb)
        
        self.firefox_path_input = QLineEdit()
        # Default Linux Firefox Path (Check Snap first, then standard)
        snap_path = os.path.join(os.path.expanduser("~"), "snap", "firefox", "common", ".mozilla", "firefox")
        std_path = os.path.join(os.path.expanduser("~"), ".mozilla", "firefox")
        
        if os.path.exists(snap_path):
            self.firefox_path_input.setText(snap_path)
        else:
            self.firefox_path_input.setText(std_path)
            
        self.firefox_path_input.textChanged.connect(self.scan_profiles)
        
        self.profile_combo = QComboBox()
        
        self.layout.addRow("Firefox Profiles Path:", self.firefox_path_input)
        self.layout.addRow("Select Profile:", self.profile_combo)
        
        self.btn_box = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        self.btn_box.addWidget(self.ok_btn)
        
        self.layout.addRow(self.btn_box)
        
        # Initial scan
        self.scan_profiles()
        
    def toggle_inputs(self, checked):
        self.firefox_path_input.setEnabled(not checked)
        self.profile_combo.setEnabled(not checked)
        
    def scan_profiles(self):
        path = self.firefox_path_input.text()
        self.profile_combo.clear()
        
        if os.path.exists(path) and os.path.isdir(path):
            profiles = []
            try:
                for entry in os.listdir(path):
                    # Firefox profiles usually end in .default or .default-release or contain alphanumeric salt
                    full_entry = os.path.join(path, entry)
                    if os.path.isdir(full_entry) and (entry.endswith(".default") or entry.endswith(".default-release") or "." in entry):
                         profiles.append(entry)
            except Exception:
                pass
            
            if not profiles:
                 self.profile_combo.addItem("No profiles found")
            else:
                 self.profile_combo.addItems(sorted(profiles))
        else:
            self.profile_combo.addItem("Invalid Path")
            
    def get_data(self):
        if self.temp_session_cb.isChecked():
            return "", ""
        return self.firefox_path_input.text(), self.profile_combo.currentText()

# --- Main Window ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhatsApp Blast Tool (Firefox Edition)")
        self.resize(1000, 700)
        
        self.user_data_dir = ""
        self.profile_dir = ""
        self.df = None
        self.image_path = None
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # --- Left Panel (Inputs) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 1. Environment Config (Button to re-open)
        env_btn = QPushButton("Configure Environment")
        env_btn.clicked.connect(self.open_env_dialog)
        left_layout.addWidget(env_btn)
        
        # 2. Excel Upload
        upload_box = QGroupBox("Data Source")
        upload_layout = QVBoxLayout()
        self.upload_btn = QPushButton("Upload Excel")
        self.upload_btn.clicked.connect(self.upload_excel)
        self.file_label = QLabel("No file selected")
        upload_layout.addWidget(self.upload_btn)
        upload_layout.addWidget(self.file_label)
        upload_box.setLayout(upload_layout)
        left_layout.addWidget(upload_box)
        
        # 3. Settings
        settings_box = QGroupBox("Sending Settings")
        settings_layout = QFormLayout()
        
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(1, 60)
        self.delay_spin.setValue(5)
        self.delay_spin.setSuffix(" sec")
        
        self.max_msg_spin = QSpinBox()
        self.max_msg_spin.setRange(1, 10000)
        self.max_msg_spin.setValue(100)
        
        settings_layout.addRow("Delay per msg:", self.delay_spin)
        settings_layout.addRow("Max Messages:", self.max_msg_spin)
        settings_box.setLayout(settings_layout)
        left_layout.addWidget(settings_box)
        
        # 4. Message Editor
        editor_box = QGroupBox("Message Editor")
        editor_layout = QVBoxLayout()
        
        # Formatting Toolbar
        toolbar_layout = QHBoxLayout()
        
        bold_btn = QPushButton("B")
        font_bold = QFont("Arial", 10)
        font_bold.setBold(True)
        bold_btn.setFont(font_bold)
        bold_btn.setFixedWidth(30)
        bold_btn.clicked.connect(lambda: self.insert_formatting("*"))
        
        italic_btn = QPushButton("I")
        font_italic = QFont("Arial", 10)
        font_italic.setItalic(True)
        italic_btn.setFont(font_italic)
        italic_btn.setFixedWidth(30)
        italic_btn.clicked.connect(lambda: self.insert_formatting("_"))
        
        strike_btn = QPushButton("S")
        font_strike = QFont("Arial", 10)
        font_strike.setStrikeOut(True)
        strike_btn.setFont(font_strike)
        strike_btn.setFixedWidth(30)
        strike_btn.clicked.connect(lambda: self.insert_formatting("~"))
        
        mono_btn = QPushButton("M")
        mono_btn.setFont(QFont("Courier New", 10))
        mono_btn.setFixedWidth(30)
        mono_btn.clicked.connect(lambda: self.insert_formatting("```"))
        
        toolbar_layout.addWidget(bold_btn)
        toolbar_layout.addWidget(italic_btn)
        toolbar_layout.addWidget(strike_btn)
        toolbar_layout.addWidget(mono_btn)
        toolbar_layout.addStretch()
        
        editor_layout.addLayout(toolbar_layout)
        
        self.msg_edit = QTextEdit()
        self.msg_edit.setPlaceholderText("Type your message here... Use {Name} to insert variables from Excel columns.")
        editor_layout.addWidget(self.msg_edit)
        
        # Image Attachment
        self.img_btn = QPushButton("Attach Image")
        self.img_btn.clicked.connect(self.select_image)
        self.img_label = QLabel("No image selected")
        editor_layout.addWidget(self.img_btn)
        editor_layout.addWidget(self.img_label)
        
        editor_box.setLayout(editor_layout)
        left_layout.addWidget(editor_box)
        
        # 5. Send Button
        self.send_btn = QPushButton("START BLAST")
        self.send_btn.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold; padding: 10px;")
        self.send_btn.setText("START BLAST (FIREFOX)")
        self.send_btn.clicked.connect(self.start_blast)
        left_layout.addWidget(self.send_btn)
        
        # --- Right Panel (Preview & Logs) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Excel Preview
        preview_box = QGroupBox("Data Preview")
        preview_layout = QVBoxLayout()
        self.table_view = QTableView()
        preview_layout.addWidget(self.table_view)
        preview_box.setLayout(preview_layout)
        right_layout.addWidget(preview_box)
        
        # Logs
        log_box = QGroupBox("Logs")
        log_layout = QVBoxLayout()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.progress_bar = QProgressBar()
        log_layout.addWidget(self.log_view)
        log_layout.addWidget(self.progress_bar)
        log_box.setLayout(log_layout)
        right_layout.addWidget(log_box)
        
        # Splitter setup
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 600])
        main_layout.addWidget(splitter)
        
        # Init Env
        self.open_env_dialog()

    def open_env_dialog(self):
        dlg = EnvDialog(self)
        if dlg.exec():
            self.user_data_dir, self.profile_dir = dlg.get_data()
            self.log(f"Environment set. Base: {self.user_data_dir} | Profile: {self.profile_dir}")

    def upload_excel(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open Excel", "", "Excel Files (*.xlsx *.xls)")
        if fname:
            try:
                self.df = pd.read_excel(fname)
                # Ensure Phone column is string
                if 'Phone' in self.df.columns:
                    self.df['Phone'] = self.df['Phone'].astype(str)
                
                self.file_label.setText(os.path.basename(fname))
                
                model = PandasModel(self.df)
                self.table_view.setModel(model)
                self.log(f"Loaded {len(self.df)} rows.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def select_image(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.gif)")
        if fname:
            self.image_path = fname
            self.img_label.setText(os.path.basename(fname))

    def insert_formatting(self, symbol):
        cursor = self.msg_edit.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(f"{symbol}{text}{symbol}")
        else:
            cursor.insertText(f"{symbol}{symbol}")
            cursor.movePosition(cursor.MoveOperation.Left, cursor.MoveMode.MoveAnchor, len(symbol))
            self.msg_edit.setTextCursor(cursor)
        self.msg_edit.setFocus()

    def log(self, message):
        self.log_view.append(message)
        # Auto scroll
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start_blast(self):
        if self.df is None:
            QMessageBox.warning(self, "Warning", "Please upload an Excel file first.")
            return
        
        msg = self.msg_edit.toPlainText()
        if not msg:
            if QMessageBox.question(self, "Confirm", "Message is empty. Continue?") != QMessageBox.StandardButton.Yes:
                return

        self.send_btn.setEnabled(False)
        self.worker = SenderWorker(
            self.df, 
            msg, 
            self.image_path, 
            self.delay_spin.value(), 
            self.max_msg_spin.value(),
            self.user_data_dir,
            self.profile_dir
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.task_finished)
        self.worker.error.connect(self.task_error)
        self.worker.start()

    def update_progress(self, val, msg):
        self.progress_bar.setValue(val)
        self.log(msg)

    def task_finished(self):
        self.send_btn.setEnabled(True)
        QMessageBox.information(self, "Done", "Automation Completed.")

    def task_error(self, err_msg):
        self.send_btn.setEnabled(True)
        self.log(f"CRITICAL ERROR: {err_msg}")
        QMessageBox.critical(self, "Error", err_msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Simple Style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
