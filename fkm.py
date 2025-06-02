#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
# gi.require_version('Notify', '0.7') # Removed: Desktop notifications replaced by in-app indicator
from gi.repository import Gtk, Gdk, GLib # Notify removed
import subprocess
import os
import threading
from pathlib import Path

class KernelManager(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Fedora Kernel Manager")
        self.set_border_width(10)
        self.set_default_size(1200, 700)

        # Desktop notifications are now replaced by in-app indicator
        # try:
        #     Notify.init("Fedora Kernel Manager")
        #     self.notifications_enabled = True
        # except GLib.Error:
        #     self.notifications_enabled = False
        #     self.log_terminal("Warning: Desktop notifications are not available. Please install libnotify-dev or similar package.")

        # --- UI Elements ---
        self.liststore = Gtk.ListStore(str)
        self.treeview = Gtk.TreeView(model=self.liststore)
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Installed Kernels", renderer, text=0)
        self.treeview.append_column(column)
        self.selection = self.treeview.get_selection()
        self.selection.set_mode(Gtk.SelectionMode.MULTIPLE)

        # Terminal-style text area for command output
        self.terminal_buffer = Gtk.TextBuffer()
        self.terminal_view = Gtk.TextView(buffer=self.terminal_buffer)
        self.terminal_view.set_editable(False)
        self.terminal_view.set_monospace(True)
        self.terminal_view.set_cursor_visible(True)
        self.terminal_view.set_name("terminal-output")
        self.terminal_view.set_can_focus(True)

        # Directly override background and text color for the terminal view
        # This is the most robust way to ensure the desired colors,
        # although override_background_color/override_color are deprecated in newer GTK versions.
        terminal_bg_color = Gdk.RGBA(0, 0, 0, 1)  # Black
        terminal_text_color = Gdk.RGBA(0, 1, 0, 1) # Green
        self.terminal_view.override_background_color(Gtk.StateFlags.NORMAL, terminal_bg_color)
        self.terminal_view.override_color(Gtk.StateFlags.NORMAL, terminal_text_color)

        # Combined treeview and terminal in a vertical paned
        self.vertical_content_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.vertical_content_paned.set_vexpand(True)
        self.vertical_content_paned.set_hexpand(True)

        scrollable_treelist = Gtk.ScrolledWindow()
        scrollable_treelist.set_hexpand(True)
        scrollable_treelist.set_vexpand(True)
        scrollable_treelist.add(self.treeview)
        self.vertical_content_paned.pack1(scrollable_treelist, resize=True, shrink=False)

        terminal_scroll = Gtk.ScrolledWindow()
        terminal_scroll.set_hexpand(True)
        terminal_scroll.set_vexpand(True)
        terminal_scroll.add(self.terminal_view)
        self.vertical_content_paned.pack2(terminal_scroll, resize=True, shrink=False)

        self.connect("show", self.on_window_show)

        self.spinner = Gtk.Spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)

        # --- In-app Status Indicator ---
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.CENTER)
        self.status_label.set_vexpand(False)
        self.status_label.set_hexpand(False)
        self.update_status_indicator("idle") # Set initial status

        # --- Buttons ---
        self.buttons_data = [
            # Kernel Management
            ("📋 عرض الأنوية", self.refresh_kernel_list),
            ("💡 الكيرنل الحالي", self.show_current_kernel),
            ("⭐ تعيين كيرنل افتراضي", self.set_default_kernel),
            ("❌ حذف المحدد", self.remove_kernels),
            ("🔎 عرض الأنوية القابلة للحذف", self.preview_old_kernels),
            ("🧹 حذف الأنوية القديمة", self.remove_old_kernels),
            ("🔍 تفاصيل النواة المحددة", self.show_selected_kernel_details_button),

            # Rescue Kernel Management
            ("♻️ تحديث نواة rescue", self.update_rescue_kernel),
            ("📁 عرض ملفات rescue", self.show_rescue_files),
            ("🗑️ إزالة rescue القديمة", self.remove_old_rescue),

            # GRUB & System Management
            ("🔄 توليد grub جديد", self.regenerate_grub),
            ("⚙️ عرض إعدادات Grub", self.show_grub_settings),
            ("🎛️ تعيين إدخال تمهيد افتراضي", self.set_default_boot_entry_by_index),
            ("📊 عرض معلومات النظام", self.show_system_info),
            ("⚙️ إدارة إعدادات DNF", self.manage_dnf_settings),
            ("📸 إنشاء لقطة Btrfs", self.create_btrfs_snapshot),
            ("🧼 Clear الشاشة", self.clear_screen),
            ("📋 نسخ مخرج الطرفية", self.copy_terminal_output),
            ("❓ حول البرنامج", self.show_about_dialog)
        ]

        # --- Button Styling ---
        css = b"""
        button {
            background-color: #fff176; /* Yellowish background */
            font-weight: bold;
            padding: 6px; /* Reduced padding for smaller buttons */
            border-radius: 5px; /* Rounded corners for buttons */
            box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2); /* Subtle shadow */
        }
        button:hover {
            background-color: #ffe082; /* Lighter yellow on hover */
        }
        button:active {
            background-color: #ffca28; /* Darker yellow when pressed */
            box-shadow: inset 1px 1px 3px rgba(0, 0, 0, 0.3); /* Inset shadow for pressed state */
        }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, style_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )

        # --- Layout ---
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.action_buttons = []
        for i, (label, callback) in enumerate(self.buttons_data):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", callback)
            grid.attach(btn, i % 2, i // 2, 1, 1) # 2 columns for buttons
            self.action_buttons.append(btn)

        right_panel_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right_panel_vbox.pack_start(grid, False, False, 0)
        right_panel_vbox.pack_start(self.spinner, False, False, 0)
        right_panel_vbox.pack_start(self.status_label, False, False, 0) # Add status label here

        # Main horizontal box: vertical_content_paned | right_panel_vbox
        main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # The left panel now only contains the vertical_content_paned (kernel list + terminal)
        main_hbox.pack_start(self.vertical_content_paned, True, True, 0)
        main_hbox.pack_start(right_panel_vbox, False, False, 0)

        self.add(main_hbox)

    def update_status_indicator(self, status_type, message=""):
        """Updates the in-app status indicator (icon/text)."""
        if status_type == "running":
            self.status_label.set_markup(f"<span foreground='#FFD700'>🔄 {message if message else 'جارٍ التنفيذ...'}</span>")
        elif status_type == "success":
            self.status_label.set_markup(f"<span foreground='#32CD32'>✅ {message if message else 'اكتمل بنجاح'}</span>")
        elif status_type == "error":
            self.status_label.set_markup(f"<span foreground='#FF4500'>❌ {message if message else 'فشل!'}</span>")
        else: # idle
            self.status_label.set_markup("<span foreground='#808080'>Idle</span>")

    def show_selected_kernel_details_button(self, widget):
        """Callback for the 'Show Selected Kernel Details' button."""
        selected_kernels = self.get_selected_kernels()
        if not selected_kernels:
            self.show_info("الرجاء تحديد نواة لعرض تفاصيلها.")
            return
        
        # Only show details for the first selected kernel if multiple are selected
        kernel_name = selected_kernels[0]
        self._show_kernel_details_in_dialog(kernel_name)

    def _show_kernel_details_in_dialog(self, kernel_name):
        """Fetches and displays detailed information for the selected kernel in a dialog."""
        def _callback(success, output):
            dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.INFO,
                                       Gtk.ButtonsType.OK, f"تفاصيل النواة: {kernel_name}")
            
            if success and output:
                dialog.format_secondary_text(output)
            else:
                dialog.format_secondary_text(f"تعذر الحصول على تفاصيل النواة: {kernel_name}\n\nيرجى التحقق من سجل الطرفية لمزيد من التفاصيل.")
            
            dialog.set_default_size(600, 400) # Set a reasonable size for the dialog
            dialog.run()
            dialog.destroy()

        # rpm -qi provides detailed info about installed package
        self.run_command_async(["rpm", "-qi", kernel_name],
                               show_output=True,
                               error_msg=f"فشل الحصول على تفاصيل {kernel_name}.",
                               callback=_callback)

    def on_window_show(self, widget):
        # Set initial position for main content paned (kernel list & terminal)
        total_height = self.vertical_content_paned.get_allocation().height
        self.vertical_content_paned.set_position(total_height // 4)
        
        self.refresh_kernel_list(None) # Automatically refresh kernel list on startup

    def log_terminal(self, text):
        """Appends text to the terminal output area and scrolls to the end."""
        end_iter = self.terminal_buffer.get_end_iter()
        self.terminal_buffer.insert(end_iter, text)
        self.terminal_view.scroll_mark_onscreen(self.terminal_buffer.get_insert())

    def set_buttons_sensitive(self, sensitive):
        """Sets the sensitivity of all action buttons."""
        for btn in self.action_buttons:
            if btn.get_label() != "🧼 Clear الشاشة": # Keep Clear Screen sensitive
                btn.set_sensitive(sensitive)

    def run_command_async(self, cmd, error_msg="حدث خطأ.", show_output=False, use_shell=False, callback=None, raise_on_error=True):
        """
        Runs a shell command asynchronously in a separate thread.
        Logs STDOUT and STDERR to the terminal view.
        Updates in-app status indicator.
        'raise_on_error': If False, a non-zero exit code will not raise CalledProcessError,
                          but 'success' in callback will be False. Useful for commands like 'grep'.
        """
        self.spinner.start()
        self.set_buttons_sensitive(False)
        self.update_status_indicator("running", "جارٍ التنفيذ...") # Set status to running

        def _run():
            success = False
            output = None
            try:
                if use_shell:
                    cmd_str = ' '.join(cmd) if isinstance(cmd, list) else cmd
                else:
                    cmd_list = cmd.split() if isinstance(cmd, str) else cmd

                GLib.idle_add(self.log_terminal, f"\n$ {cmd_str if use_shell else ' '.join(cmd_list)}\n")

                result = subprocess.run(cmd_list if not use_shell else cmd_str,
                                        capture_output=True, text=True, check=raise_on_error, shell=use_shell)

                if result.stdout:
                    GLib.idle_add(self.log_terminal, f"STDOUT:\n{result.stdout.strip()}\n")
                if result.stderr:
                    GLib.idle_add(self.log_terminal, f"STDERR:\n{result.stderr.strip()}\n")

                if show_output:
                    output = result.stdout.strip()
                
                # Determine success based on return code if raise_on_error is False
                if not raise_on_error and result.returncode != 0:
                    success = False
                    GLib.idle_add(self.log_terminal, f"Command exited with non-zero status: {result.returncode}\n")
                else:
                    success = True

                if success:
                    self.update_status_indicator("success", "اكتمل بنجاح")
                else:
                    error_details = result.stderr.strip() if result.stderr else result.stdout.strip() if result.stdout else f"الرمز: {result.returncode}"
                    self.update_status_indicator("error", "فشل!")
                    GLib.idle_add(self.show_error, f"{error_msg}\nالخطأ: {error_details}")

            except subprocess.CalledProcessError as e:
                if e.stdout:
                    GLib.idle_add(self.log_terminal, f"ERROR STDOUT:\n{e.stdout.strip()}\n")
                if e.stderr:
                    GLib.idle_add(self.log_terminal, f"ERROR STDERR:\n{e.stderr.strip()}\n")
                error_details = e.stderr.strip() if e.stderr else e.stdout.strip() if e.stdout else "خطأ غير معروف."
                self.update_status_indicator("error", "فشل!")
                GLib.idle_add(self.show_error, f"{error_msg}\nالخطأ: {error_details}")
            except FileNotFoundError:
                self.update_status_indicator("error", "فشل!")
                GLib.idle_add(self.show_error, f"الأمر غير موجود أو حدث خطأ في المسار.")
            finally:
                GLib.idle_add(self.spinner.stop)
                GLib.idle_add(self.set_buttons_sensitive, True)
                if callback:
                    callback(success, output)

        threading.Thread(target=_run).start()

    def get_selected_kernels(self):
        model, paths = self.selection.get_selected_rows()
        return [model.get_value(model.get_iter(path), 0) for path in paths]

    def refresh_kernel_list(self, widget):
        self.run_command_async(["rpm", "-q", "kernel"],
                               error_msg="فشل عرض قائمة الأنوية.",
                               show_output=True,
                               use_shell=False,
                               callback=lambda s, o: (self.liststore.clear(), [self.liststore.append([line.strip()]) for line in o.splitlines()]) if s and o else None)

    def show_current_kernel(self, widget):
        self.run_command_async(["/usr/bin/uname", "-r"],
                               show_output=True,
                               error_msg="فشل عرض النواة الحالية.",
                               callback=lambda s, o: self.show_info(f"النواة الحالية:\n{o}") if s and o else self.show_info("تعذر الحصول على النواة الحالية أو لا يوجد مخرج. يرجى التحقق من سجل الطرفية لمزيد من التفاصيل."))

    def set_default_kernel(self, widget):
        selected = self.get_selected_kernels()
        if not selected:
            self.show_info("الرجاء تحديد كيرنل لتعيينه كافتراضي.")
            return
        if len(selected) > 1:
            self.show_info("الرجاء تحديد كيرنل واحد فقط لتعيينه كافتراضي.")
            return

        kernel = selected[0]
        version = kernel.replace("kernel-", "")
        path = f"/boot/vmlinuz-{version}"

        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.YES_NO, "هل تريد تعيين هذا الكيرنل كافتراضي؟")
        dialog.format_secondary_text(f"سيتم تعيين '{kernel}' كيرنل افتراضي. ستحتاج إلى إعادة تشغيل النظام لتطبيق التغيير.")
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            self.run_command_async(["pkexec", "grubby", "--set-default", path],
                                   error_msg="فشل تعيين الكيرنل الافتراضي.",
                                   show_output=False,
                                   use_shell=False,
                                   callback=lambda s, o: (self.refresh_kernel_list(None), self.show_info("تم تعيين الكيرنل الافتراضي بنجاح. أعد تشغيل النظام لتطبيق التغييرات.")) if s else None)

    def remove_kernels(self, widget):
        kernels = self.get_selected_kernels()
        if not kernels:
            self.show_info("الرجاء تحديد أنوية لحذفها.")
            return

        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.YES_NO, "هل تريد حذف الأنوية المحددة؟")
        dialog.format_secondary_text("قد يؤثر حذف الأنوية على استقرار النظام.\n\n" + "\n".join(kernels))
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            self.run_command_async(["pkexec", "dnf", "remove", "-y"] + kernels,
                                   error_msg="فشل حذف الأنوية.",
                                   show_output=False,
                                   use_shell=False,
                                   callback=lambda s, o: (self.refresh_kernel_list(None), self.show_info("تم حذف الأنوية بنجاح.")) if s else None)

    def preview_old_kernels(self, widget):
        self.run_command_async(["dnf", "repoquery", "--installonly", "--latest-limit=-1", "-q"],
                               show_output=True,
                               error_msg="فشل عرض الأنوية القابلة للحذف.",
                               use_shell=False,
                               callback=lambda s, o: self.show_info("الأنوية القابلة للحذف:\n" + o) if s and o else self.show_info("لا توجد أنوية قديمة قابلة للحذف حاليًا."))

    def remove_old_kernels(self, widget):
        """
        Removes old, unused kernels after user confirmation.
        """
        def _get_old_kernels_callback(success, output):
            if not success or not output:
                self.show_info("لا توجد أنوية قديمة للحذف.")
                return

            kernels_to_remove = output.splitlines()
            dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                       Gtk.ButtonsType.YES_NO, "هل تريد حذف الأنوية القديمة؟")
            dialog.format_secondary_text("قد يؤثر حذف الأنوية القديمة على خيارات التمهيد.\n\n" + "\n".join(kernels_to_remove))
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                self.run_command_async(["pkexec", "dnf", "remove", "-y"] + kernels_to_remove,
                                       error_msg="فشل حذف الأنوية القديمة.",
                                       show_output=False,
                                       use_shell=False,
                                       callback=lambda s, o: (self.refresh_kernel_list(None), self.show_info("تم حذف الأنوية بنجاح.")) if s else None)

        self.run_command_async(["dnf", "repoquery", "--installonly", "--latest-limit=-1", "-q"],
                               show_output=True,
                               use_shell=False,
                               callback=_get_old_kernels_callback)

    def clear_screen(self, widget):
        self.terminal_buffer.set_text("")
        self.liststore.clear()
        self.update_status_indicator("idle") # Reset status on clear screen

    def copy_terminal_output(self, widget):
        """Copies the entire content of the terminal output to the clipboard."""
        text = self.terminal_buffer.get_text(
            self.terminal_buffer.get_start_iter(),
            self.terminal_buffer.get_end_iter(),
            True
        )
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        self.show_info("تم نسخ مخرج الطرفية إلى الحافظة.")
        self.update_status_indicator("success", "تم نسخ مخرج الطرفية.")

    def show_grub_settings(self, widget):
        """Displays the current GRUB settings using grubby --info ALL."""
        self.run_command_async(["pkexec", "grubby", "--info", "ALL"],
                               show_output=True,
                               error_msg="فشل عرض إعدادات Grub. قد تحتاج إلى صلاحيات الجذر.",
                               use_shell=False,
                               callback=lambda s, o: self.show_info(f"إعدادات Grub:\n{o}") if s and o else self.show_info("تعذر الحصول على إعدادات Grub أو لا يوجد مخرج. يرجى التحقق من سجل الطرفية لمزيد من التفاصيل."))

    def show_grub_boot_entries(self, widget):
        """Displays a list of GRUB boot entry titles."""
        def _callback(success, output):
            if not success or not output:
                self.show_info("تعذر الحصول على إدخالات التمهيد أو لا يوجد مخرج. يرجى التحقق من سجل الطرفية لمزيد من التفاصيل.")
                return

            titles = []
            for line in output.splitlines():
                if line.startswith("title="):
                    titles.append(line.replace("title=", "").strip())
            
            if titles:
                self.show_info("إدخالات التمهيد (Grub Entries):\n" + "\n".join(titles))
            else:
                self.show_info("لم يتم العثور على إدخالات تمهيد في مخرجات Grub.")
            self.update_status_indicator("success", "تم عرض إدخالات التمهيد.")

        self.run_command_async(["pkexec", "grubby", "--info", "ALL"],
                               show_output=True,
                               error_msg="فشل عرض إدخالات التمهيد. قد تحتاج إلى صلاحيات الجذر.",
                               use_shell=False,
                               callback=_callback)

    def set_default_boot_entry_by_index(self, widget):
        """Allows user to set a default GRUB boot entry by index."""
        def _get_entries_callback(success, output):
            if not success or not output:
                self.show_error("تعذر الحصول على إدخالات التمهيد لتعيين الافتراضي.")
                return

            entries = [] # Stores (index, title)
            current_index = -1
            current_title = ""
            
            for line in output.splitlines():
                if line.startswith("index="):
                    # If we processed a previous entry, add it to list
                    if current_title:
                        entries.append((str(current_index), current_title))
                    current_index = int(line.replace("index=", "").strip())
                    current_title = "" # Reset title for new entry
                elif line.startswith("title="):
                    current_title = line.replace("title=", "").strip()
            
            # Add the last entry after loop finishes
            if current_title:
                entries.append((str(current_index), current_title))


            if not entries:
                self.show_info("لا توجد إدخالات تمهيد متاحة لتعيينها كافتراضي.")
                return

            # Create a dialog to select the index
            dialog = Gtk.Dialog(title="تعيين إدخال التمهيد الافتراضي", parent=self,
                                flags=Gtk.DialogFlags.MODAL, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK))
            dialog.set_default_size(400, 300)
            
            label = Gtk.Label("الرجاء اختيار فهرس إدخال التمهيد الافتراضي:")
            dialog.get_content_area().pack_start(label, False, False, 5)

            liststore = Gtk.ListStore(str, str) # Index, Title
            for index, title in entries:
                liststore.append([index, title])
            
            treeview = Gtk.TreeView(model=liststore)
            renderer_index = Gtk.CellRendererText()
            treeview.append_column(Gtk.TreeViewColumn("الفهرس", renderer_index, text=0))
            renderer_title = Gtk.CellRendererText()
            treeview.append_column(Gtk.TreeViewColumn("العنوان", renderer_title, text=1))
            
            scrollable = Gtk.ScrolledWindow()
            scrollable.set_vexpand(True)
            scrollable.add(treeview)
            dialog.get_content_area().pack_start(scrollable, True, True, 5)
            
            dialog.show_all()
            
            response = dialog.run()
            
            selected_index = -1
            if response == Gtk.ResponseType.OK:
                selection = treeview.get_selection()
                model, treeiter = selection.get_selected()
                if treeiter:
                    selected_index = int(model.get_value(treeiter, 0)) # Get index as int
            
            dialog.destroy()

            if selected_index != -1:
                self.run_command_async(["pkexec", "grubby", "--set-default-index", str(selected_index)],
                                       error_msg=f"فشل تعيين إدخال التمهيد الافتراضي إلى الفهرس {selected_index}.",
                                       show_output=False,
                                       use_shell=False,
                                       callback=lambda s, o: self.show_info(f"تم تعيين إدخال التمهيد الافتراضي بنجاح إلى الفهرس {selected_index}. أعد تشغيل النظام لتطبيق التغييرات.") if s else None)
            else:
                self.show_info("لم يتم اختيار فهرس.")

        self.run_command_async(["pkexec", "grubby", "--info", "ALL"],
                               show_output=True,
                               error_msg="فشل الحصول على إدخالات التمهيد لتعيين الافتراضي.",
                               use_shell=False,
                               callback=_get_entries_callback)

    def show_system_info(self, widget):
        """Displays basic system information."""
        def _callback(success, output):
            if not success or not output:
                self.show_info("تعذر الحصول على معلومات النظام.")
                return

            info_lines = output.splitlines()
            display_info = []
            
            # --- OS Release ---
            os_release_path = "/etc/os-release"
            if os.path.exists(os_release_path):
                try:
                    with open(os_release_path, 'r') as f:
                        os_lines = f.readlines()
                        for line in os_lines:
                            if line.startswith("PRETTY_NAME="):
                                display_info.append(line.replace("PRETTY_NAME=", "إصدار نظام التشغيل: ").strip().strip('"'))
                                break
                except Exception as e:
                    GLib.idle_add(self.log_terminal, f"Error reading {os_release_path}: {e}\n")

            # --- CPU ---
            cpu_model = ""
            for line in info_lines:
                if "Model name:" in line:
                    cpu_model = line.replace("Model name:", "المعالج:").strip()
                    display_info.append(cpu_model)
                    break
            
            # --- Architecture ---
            arch = ""
            for line in info_lines:
                if "Architecture:" in line:
                    arch = line.replace("Architecture:", "البنية:").strip()
                    display_info.append(arch)
                    break

            # --- RAM ---
            # Try to get RAM from 'free -b'
            ram_info = ""
            for line in info_lines:
                if "Mem:" in line: # free -b output line
                    parts = line.split()
                    if len(parts) > 1:
                        total_mem_bytes = int(parts[1])
                        # Convert bytes to GiB for readability
                        total_mem_gib = round(total_mem_bytes / (1024**3), 2)
                        ram_info = f"الذاكرة الكلية (RAM): {total_mem_gib} GiB"
                        display_info.append(ram_info)
                        break

            # Fallback if specific lines weren't found or raw output is better
            if not display_info:
                display_info = info_lines

            self.show_info("معلومات النظام:\n" + "\n".join(display_info))
            self.update_status_indicator("success", "تم عرض معلومات النظام.")

        # Commands to get system info: /etc/os-release is read directly
        # lscpu for CPU/architecture, free -b for memory
        cmd = [
            "lscpu | grep 'Model name'",
            "lscpu | grep 'Architecture'",
            "free -b | grep Mem:"
        ]
        # Use shell=True to allow piping and multiple commands in one run
        self.run_command_async(" ; ".join(cmd),
                               show_output=True,
                               error_msg="فشل الحصول على معلومات النظام.",
                               use_shell=True,
                               callback=_callback)

    def manage_dnf_settings(self, widget):
        """Opens a dialog to manage DNF settings like installonly_limit."""
        config_path = "/etc/dnf/dnf.conf"
        
        dialog = Gtk.Dialog(title="إعدادات DNF", parent=self,
                            flags=Gtk.DialogFlags.MODAL, buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK))
        dialog.set_default_size(400, 200)
        
        content_area = dialog.get_content_area()
        
        # Current installonly_limit
        current_limit_label = Gtk.Label(label="الحد الحالي للأنوية المثبتة (installonly_limit):")
        self.current_limit_value_label = Gtk.Label(label="جارٍ التحميل...")
        
        hbox_current = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox_current.pack_start(current_limit_label, False, False, 0)
        hbox_current.pack_start(self.current_limit_value_label, False, False, 0)
        content_area.pack_start(hbox_current, False, False, 5)

        # New installonly_limit
        new_limit_label = Gtk.Label(label="تعيين حد جديد:")
        self.new_limit_entry = Gtk.Entry()
        self.new_limit_entry.set_width_chars(5)
        self.new_limit_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.new_limit_entry.set_placeholder_text("3-5") # Typical values
        
        hbox_new = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox_new.pack_start(new_limit_label, False, False, 0)
        hbox_new.pack_start(self.new_limit_entry, False, False, 0)
        content_area.pack_start(hbox_new, False, False, 5)

        # Read current limit
        def _read_limit_callback(success, output):
            if success and output: # success is True if grep found the line (returncode 0)
                try:
                    limit = output.strip().split('=')[-1]
                    self.current_limit_value_label.set_text(limit)
                    self.new_limit_entry.set_text(limit)
                except (IndexError, ValueError):
                    self.current_limit_value_label.set_text("خطأ في القراءة")
                    GLib.idle_add(self.log_terminal, f"DEBUG: Failed to parse installonly_limit from: '{output}'\n")
            else: # success is False if grep didn't find the line (returncode 1) or other issue
                self.current_limit_value_label.set_text("3 (افتراضي)") # Assume default if not found
                self.new_limit_entry.set_text("3") # Set default in entry too
                GLib.idle_add(self.log_terminal, "DEBUG: installonly_limit not found in config or failed to read. Using default '3'.\n")
            self.update_status_indicator("idle") # Reset status after reading

        # Using grep directly on the file path for current value
        # pkexec is needed to read /etc/dnf/dnf.conf if permissions are strict
        self.run_command_async(["pkexec", "grep", "^installonly_limit", config_path],
                               show_output=True,
                               error_msg="فشل قراءة installonly_limit من dnf.conf.",
                               callback=lambda s, o: _read_limit_callback(s, o),
                               raise_on_error=False) # Important: Don't raise error if grep doesn't find match

        dialog.show_all()
        response = dialog.run()
        
        if response == Gtk.ResponseType.OK:
            new_limit_str = self.new_limit_entry.get_text().strip()
            if new_limit_str.isdigit():
                new_limit = int(new_limit_str)
                if 1 <= new_limit <= 10: # Reasonable range for installonly_limit
                    # Write new limit to dnf.conf
                    # This command handles both cases: replacing an existing line or appending a new one.
                    sed_cmd = f"pkexec bash -c \"grep -q '^installonly_limit=' {config_path} && pkexec sed -i '/^installonly_limit=/c\\installonly_limit={new_limit}' {config_path} || pkexec sh -c 'echo \"installonly_limit={new_limit}\" >> {config_path}'\""
                    
                    self.run_command_async(sed_cmd,
                                           error_msg=f"فشل تعيين installonly_limit إلى {new_limit}.",
                                           use_shell=True,
                                           callback=lambda s, o: self.show_info(f"تم تعيين installonly_limit إلى {new_limit} بنجاح.") if s else None)
                else:
                    self.show_error("الحد الجديد يجب أن يكون رقماً بين 1 و 10.")
            else:
                self.show_error("الحد الجديد يجب أن يكون رقماً صحيحاً.")
        
        dialog.destroy()

    def create_btrfs_snapshot(self, widget):
        """Creates a Btrfs snapshot if the root filesystem is Btrfs and snapper is installed."""
        def _check_btrfs_and_snapper_callback(success, output):
            if not success:
                self.show_error("فشل التحقق من نظام الملفات أو snapper. يرجى التحقق من سجل الطرفية.")
                return

            output_lines = output.splitlines()
            is_btrfs_root = False
            snapper_installed = False
            
            for line in output_lines:
                if "btrfs" in line and "/" in line: # Simpler check for btrfs root
                    is_btrfs_root = True
                if "snapper" in line and "/usr/bin/snapper" in line: # Check for snapper existence
                    snapper_installed = True

            if not is_btrfs_root:
                self.show_info("نظام ملفات الجذر ليس Btrfs. لا يمكن إنشاء لقطة Btrfs.")
                return
            if not snapper_installed:
                self.show_info("أداة Snapper غير مثبتة. لا يمكن إنشاء لقطة Btrfs.")
                return

            # Proceed to create snapshot
            dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                       Gtk.ButtonsType.YES_NO, "هل تريد إنشاء لقطة Btrfs (snapshot) الآن؟")
            dialog.format_secondary_text("سيتم إنشاء لقطة لنظام الجذر. هذا مفيد قبل إجراء تغييرات كبيرة على النواة.")
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                self.run_command_async(["pkexec", "snapper", "--no-dbus", "create", "--description", "Before_Kernel_Operation", "--type", "pre"],
                                       error_msg="فشل إنشاء لقطة Btrfs.",
                                       show_output=False,
                                       use_shell=False,
                                       callback=lambda s, o: self.show_info("تم إنشاء لقطة Btrfs بنجاح.") if s else None)
            
        # Check if root is Btrfs and snapper is installed
        check_cmd = "findmnt -n -o FSTYPE,TARGET / ; which snapper"
        self.run_command_async(check_cmd,
                               show_output=True,
                               error_msg="فشل التحقق من بيئة Btrfs/Snapper.",
                               use_shell=True,
                               callback=_check_btrfs_and_snapper_callback)

    def update_rescue_kernel(self, widget):
        """Updates the rescue kernel to the current running kernel using kernel-install."""
        def _get_current_kernel_callback(success, current_kernel_version):
            if not success or not current_kernel_version:
                self.show_error("تعذر الحصول على إصدار النواة الحالي.")
                return

            # Ensure current_kernel_version is stripped of any whitespace
            current_kernel_version = current_kernel_version.strip()
            vmlinuz_path = f"/lib/modules/{current_kernel_version}/vmlinuz"
            
            if not os.path.exists(vmlinuz_path):
                self.show_error(f"مسار vmlinuz للنواة الحالية غير موجود:\n{vmlinuz_path}\nالرجاء التأكد من تثبيت النواة بشكل صحيح.")
                return

            self.run_command_async(["pkexec", "kernel-install", "add", current_kernel_version, vmlinuz_path],
                                   error_msg="فشل تحديث نواة rescue.",
                                   show_output=False,
                                   use_shell=False,
                                   callback=lambda s, o: self.show_info("تم تحديث نواة rescue بنجاح.") if s else None)

        self.run_command_async(["/usr/bin/uname", "-r"],
                               error_msg="فشل الحصول على النواة الحالية لتحديث rescue.",
                               show_output=True,
                               use_shell=False,
                               callback=_get_current_kernel_callback)

    def show_rescue_files(self, widget):
        # Using 'ls -l' and filtering with grep to show relevant rescue files with details
        self.run_command_async("ls -l /boot/ | grep -E 'vmlinuz-rescue|initramfs-rescue'",
                               show_output=True,
                               error_msg="فشل عرض ملفات rescue.",
                               use_shell=True, # Use shell for grep pipe
                               callback=lambda s, f: self.show_info("ملفات rescue:\n" + f) if s and f else self.show_info("لا توجد ملفات rescue في المسارات المتوقعة."))

    def remove_old_rescue(self, widget):
        """Removes old rescue kernel files from /boot, keeping the current kernel's rescue files."""
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.YES_NO, "هل تريد إزالة ملفات rescue القديمة؟")
        dialog.format_secondary_text("سيتم حذف ملفات rescue المرتبطة بالأنوية القديمة فقط. سيتم الاحتفاظ بملفات rescue الخاصة بالنواة الحالية.")
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            # Step 1: Get the current kernel version
            self.run_command_async(["/usr/bin/uname", "-r"],
                                   show_output=True,
                                   error_msg="فشل الحصول على النواة الحالية لتحديد ملفات rescue القديمة.",
                                   callback=self._process_rescue_removal_with_current_kernel)

    def _process_rescue_removal_with_current_kernel(self, success, current_kernel_version):
        """Callback to process rescue removal after getting current kernel version."""
        if not success or not current_kernel_version:
            self.show_error("تعذر تحديد النواة الحالية لإزالة ملفات rescue القديمة.")
            return

        current_kernel_base = current_kernel_version.strip() # Ensure no leading/trailing whitespace

        # Step 2: List all rescue files
        # Using find to get full paths and filter out directories
        self.run_command_async("find /boot -maxdepth 1 -type f -regex '.*/\\(vmlinuz\\|initramfs\\)-rescue-.*\\(\\.img\\)?' 2>/dev/null",
                               show_output=True,
                               use_shell=True,
                               error_msg="فشل عرض ملفات rescue.",
                               callback=lambda s, output: self._filter_and_remove_rescue_files(s, output, current_kernel_base))

    def _filter_and_remove_rescue_files(self, success, all_rescue_files_output, current_kernel_base):
        """Filters rescue files and prompts for removal."""
        if not success or not all_rescue_files_output:
            self.show_info("لا توجد ملفات rescue قابلة للإزالة حاليًا.")
            return

        all_rescue_files = all_rescue_files_output.splitlines()
        files_to_remove = []

        for f_path in all_rescue_files:
            filename = os.path.basename(f_path)
            version_match = None
            # Extract version from filename
            if filename.startswith("vmlinuz-rescue-"):
                version_match = filename.replace("vmlinuz-rescue-", "")
            elif filename.startswith("initramfs-rescue-"):
                version_match = filename.replace("initramfs-rescue-", "").replace(".img", "")

            # If a version is extracted and it's NOT the current kernel's version, add to removal list
            # Also, ensure we don't remove files that are not clearly associated with a kernel version
            if version_match and version_match != current_kernel_base:
                files_to_remove.append(f_path)

        if not files_to_remove:
            self.show_info("لا توجد ملفات rescue قديمة مرتبطة بأنوية سابقة للحذف.")
            return

        confirm_dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.QUESTION,
                                           Gtk.ButtonsType.YES_NO, "تأكيد حذف الملفات التالية:")
        confirm_dialog.format_secondary_text("سيتم حذف ملفات rescue التالية:\n" + "\n".join(files_to_remove))
        confirm_response = confirm_dialog.run()
        confirm_dialog.destroy()

        if confirm_response == Gtk.ResponseType.YES:
            self.run_command_async(["pkexec", "rm", "-f"] + files_to_remove,
                                   error_msg="فشل إزالة ملفات rescue القديمة.",
                                   show_output=False,
                                   use_shell=False,
                                   callback=lambda s, o: self.show_info("تمت إزالة ملفات rescue القديمة بنجاح.") if s else None)

    def regenerate_grub(self, widget):
        self.run_command_async(["pkexec", "grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"],
                               error_msg="فشل توليد grub جديد.",
                               show_output=False,
                               use_shell=False,
                               callback=lambda s, o: self.show_info("تم توليد grub جديد بنجاح.") if s else None)

    def show_about_dialog(self, widget):
        """Displays an about dialog for the application."""
        about_dialog = Gtk.AboutDialog()
        about_dialog.set_program_name("Fedora Kernel Manager")
        about_dialog.set_version("1.0")
        about_dialog.set_copyright("© NaGaR Free Softwares النجار للبرمجيات الحرة 2025") # You can change this
        about_dialog.set_comments("أداة بسيطة لإدارة نواة Linux في نظام فيدورا.")
        about_dialog.set_website("https://fb.com/nagasky") # Optional website link
        about_dialog.set_website_label("الموقع الإلكتروني")
        about_dialog.set_authors(["Mahmoud Al Nagar محمود النجار"]) # Replace with your name
        about_dialog.set_license_type(Gtk.License.MIT_X11) # Or Gtk.License.GPL_3_0
        about_dialog.set_wrap_license(True)
        
        about_dialog.run()
        about_dialog.destroy()

    def show_info(self, message):
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.INFO,
                                   Gtk.ButtonsType.OK, message)
        dialog.run()
        dialog.destroy()

    def show_error(self, message):
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.ERROR,
                                   Gtk.ButtonsType.OK, message)
        dialog.run()
        dialog.destroy()

if __name__ == "__main__":
    win = KernelManager()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

