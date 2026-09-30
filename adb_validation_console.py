"""ADB Validation Console: portable Windows desktop front end for Android Platform Tools."""
from __future__ import annotations
import datetime as dt
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from command_library import COMMANDS, INFO_PROPS, SNAPSHOT
from config_manager import BASE, Config
from platform_tools import PlatformToolsManager, parse_devices, friendly_error
from remote_browser import RemoteEntry, child_path, display_size, list_command, normalize_remote_path, parent_path, parse_long_listing, safe_push_target

OUT = BASE / 'ADB_Output'
BG = '#0C121A'
SIDEBAR = '#101B27'
PANEL = '#152331'
CARD = '#1B2D3C'
BORDER = '#2A4051'
TEXT = '#EAF3F7'
MUTED = '#9AB0BE'
ACCENT = '#56C7DA'
GREEN = '#52D5A4'
AMBER = '#E8B86B'
RED = '#F08080'
UI_FONT = 'Segoe UI' if os.name == 'nt' else 'Helvetica Neue'
MONO_FONT = 'Consolas' if os.name == 'nt' else 'Menlo'
for folder in ('Bugreports','Logcat','Screenshots','ScreenRecords','Pulls','Reports','SupportBundle'):
    (OUT / folder).mkdir(parents=True, exist_ok=True)

def stamp(): return dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
def clock(): return dt.datetime.now().strftime('%H:%M:%S')
def safe_serial(serial): return re.sub(r'[^A-Za-z0-9._-]', '_', serial or 'device')
def filter_lines(text, expression):
    if not expression: return text
    try: rx = re.compile(expression, re.I)
    except re.error: rx = re.compile(re.escape(expression), re.I)
    return '\n'.join(line for line in text.splitlines() if rx.search(line))

def classify_manual(args):
    low = [x.lower() for x in args]
    joined = ' '.join(low)
    if any(x in joined for x in ('factory reset','format ','wipe','unlock','flash ','setenforce','rm -','rm -r','mkfs')):
        return 'BLOCKED'
    if any(x in joined for x in ('pm clear','uninstall','disable-user','reboot','root','unroot','logcat -c','screenrecord',' input keyevent')):
        return 'DESTRUCTIVE' if any(x in joined for x in ('pm clear','uninstall','disable-user','reboot')) else 'CAUTION'
    if any(x in joined for x in (' push ',' tcpip ',' install','am force-stop','monkey -p','pm enable')):
        return 'CAUTION'
    return 'SAFE'

class Tooltip:
    def __init__(self, widget, text):
        self.widget=widget; self.text=text; self.popup=None
        widget.bind('<Enter>',self.show,add='+')
        widget.bind('<Leave>',self.hide,add='+')
        widget.bind('<ButtonPress>',self.hide,add='+')
    def show(self,event=None):
        if self.popup or not self.text:return
        self.popup=tk.Toplevel(self.widget); self.popup.wm_overrideredirect(True)
        self.popup.wm_geometry(f'+{self.widget.winfo_rootx()+10}+{self.widget.winfo_rooty()+self.widget.winfo_height()+4}')
        tk.Label(self.popup,text=self.text,bg='#f0f5f7',fg='#18242d',padx=8,pady=5,
                 font=('Segoe UI',9),justify='left').pack()
    def hide(self,event=None):
        if self.popup:self.popup.destroy(); self.popup=None

class Dropdown(tk.Frame):
    def __init__(self,parent,variable,choices=(),width=26,on_select=None,background=CARD):
        super().__init__(parent,bg=background,highlightbackground=BORDER,highlightthickness=1)
        self.variable=variable; self.choices=list(choices); self.on_select=on_select
        self.label=tk.Label(self,textvariable=variable,bg=background,fg=TEXT,font=(UI_FONT,9),
                            width=width,anchor='w',padx=8,pady=7,cursor='hand2',takefocus=1)
        self.label.pack(side='left')
        self.arrow=tk.Label(self,text='▾',bg=background,fg=MUTED,font=(UI_FONT,11),padx=7,cursor='hand2')
        self.arrow.pack(side='right')
        self.menu=tk.Menu(self,tearoff=0)
        for widget in (self,self.label,self.arrow): widget.bind('<Button-1>',self.show)
        self.label.bind('<Return>',self.show); self.label.bind('<space>',self.show)
    def __setitem__(self,key,value):
        if key!='values': raise KeyError(key)
        self.choices=list(value)
    def show(self,event=None):
        self.menu.delete(0,'end')
        if not self.choices: self.menu.add_command(label='No options available',state='disabled')
        for choice in self.choices:
            self.menu.add_command(label=choice,command=lambda value=choice:self.select(value))
        try: self.menu.tk_popup(self.winfo_rootx(),self.winfo_rooty()+self.winfo_height())
        finally: self.menu.grab_release()
    def select(self,value):
        self.variable.set(value)
        if self.on_select:self.on_select()

class ScrollPane(ttk.Frame):
    def __init__(self,parent,width=None,background=BG):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,background=background,highlightthickness=0,width=width or 1)
        self.scrollbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview,
                                     style='Dark.Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left',fill='both',expand=True)
        self.scrollbar.pack(side='right',fill='y')
        self.content=tk.Frame(self.canvas,bg=background,padx=14,pady=14)
        self.window=self.canvas.create_window((0,0),window=self.content,anchor='nw')
        self.content.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.window,width=e.width))
        self.canvas.bind('<MouseWheel>',self._wheel)
        self.content.bind('<MouseWheel>',self._wheel)
    def _wheel(self,event):
        self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
    def reset(self): self.canvas.yview_moveto(0)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_data = Config()
        self.preview_mode = '--preview' in sys.argv
        self.tools = PlatformToolsManager(self.config_data.data['platform_tools'], source=__file__)
        self.jobs = queue.Queue()
        self.devices = []
        self.stream = None
        self.active_stops = []
        self.busy = 0
        self.page = 'Dashboard'
        self.last_args = None
        self.last_device = None
        self.browser_location = '/sdcard'
        self.browser_request_id = 0
        self.browser_items = {}
        self.title('ADB Validation Console')
        self.geometry(self.config_data.data.get('geometry','1500x900'))
        self.minsize(1100,650)
        self.configure(bg=BG)
        self._style()
        self._layout()
        self._shortcuts()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100,self._drain)
        self.after(300,self._startup)
        self.after(12000,self._periodic_refresh)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=TEXT, fieldbackground=PANEL, font=(UI_FONT,10))
        s.configure('TFrame', background=BG)
        s.configure('TLabel', background=BG, foreground=TEXT)
        s.configure('TButton', background=CARD, foreground=TEXT, padding=(13,9), borderwidth=0, font=(UI_FONT,10,'bold'))
        s.map('TButton', background=[('active','#28475A')])
        s.configure('Accent.TButton', background='#147B91', foreground='white', padding=(14,10))
        s.map('Accent.TButton', background=[('active','#1A9AB1')])
        s.configure('Danger.TButton', background='#703C43', foreground='white', padding=(13,9))
        s.configure('Caution.TButton', background='#67502B', foreground='white', padding=(13,9))
        s.configure('Quiet.TButton', background=PANEL, foreground=MUTED, padding=(10,7), font=(UI_FONT,9))
        s.map('Quiet.TButton', background=[('active',CARD)])
        s.configure('TEntry', padding=6, fieldbackground=PANEL, foreground=TEXT)
        s.configure('TCombobox', padding=6, fieldbackground=PANEL, foreground=TEXT)
        s.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=30)
        s.configure('Treeview.Heading', background=CARD, foreground=TEXT)
        s.configure('Dark.Vertical.TScrollbar',background=BORDER,troughcolor=SIDEBAR,
                    arrowcolor=MUTED,bordercolor=SIDEBAR,darkcolor=BORDER,lightcolor=BORDER,
                    relief='flat',borderwidth=0,width=9)
        s.map('Dark.Vertical.TScrollbar',background=[('active','#3D6173')])
        s.configure('TCheckbutton',background=PANEL,foreground=MUTED,font=(UI_FONT,9))

    def _layout(self):
        header=tk.Frame(self,bg=SIDEBAR,padx=22,pady=15); header.pack(fill='x')
        mark=tk.Label(header,text='AV',bg='#147B91',fg='white',width=3,height=2,font=(UI_FONT,13,'bold'))
        mark.pack(side='left',padx=(0,13))
        brand=tk.Frame(header,bg=SIDEBAR); brand.pack(side='left')
        tk.Label(brand,text='ADB Validation Console',bg=SIDEBAR,fg=TEXT,font=(UI_FONT,16,'bold')).pack(anchor='w')
        tk.Label(brand,text='DEVICE OPERATIONS  /  AUTOMOTIVE VALIDATION',bg=SIDEBAR,fg=MUTED,font=(UI_FONT,8,'bold')).pack(anchor='w',pady=(2,0))
        controls=tk.Frame(header,bg=SIDEBAR); controls.pack(side='right')
        self.status = tk.StringVar(value='SEARCHING')
        self.connection_state=tk.StringVar(value='NO DEVICE')
        self._pill(controls,self.status,ACCENT).pack(side='left',padx=(0,8))
        self._pill(controls,self.connection_state,AMBER).pack(side='left',padx=(0,14))
        self.device_var = tk.StringVar(value='No devices detected')
        self.selector = Dropdown(controls,self.device_var,width=28,on_select=self._device_selected)
        self.selector.pack(side='left',padx=(0,8))
        ttk.Button(controls,text='Refresh',command=self.refresh_devices,style='Quiet.TButton').pack(side='left')
        strip=tk.Frame(self,bg=PANEL,padx=23,pady=10); strip.pack(fill='x')
        self.detail = tk.StringVar(value='No device selected  ·  Android —  ·  Build —  ·  Root —  ·  SELinux —')
        tk.Label(strip,textvariable=self.detail,bg=PANEL,fg=MUTED,font=(UI_FONT,10),anchor='w').pack(fill='x')
        self.preview=tk.StringVar(value='—')
        footer=tk.Frame(self,bg=SIDEBAR,padx=20,pady=9); footer.pack(side='bottom',fill='x')
        tk.Label(footer,text='COMMAND PREVIEW',bg=SIDEBAR,fg=ACCENT,font=(UI_FONT,8,'bold')).pack(side='left',padx=(0,12))
        self.preview_label=tk.Label(footer,textvariable=self.preview,bg=SIDEBAR,fg=MUTED,
                                    font=(MONO_FONT,9),anchor='w',cursor='hand2')
        self.preview_label.pack(side='left',fill='x',expand=True)
        self.preview_label.bind('<Button-1>',lambda e:self._copy_preview())
        Tooltip(self.preview_label,'Click to copy the displayed ADB command')
        body = ttk.Panedwindow(self,orient='vertical'); body.pack(fill='both',expand=True)
        self.body=body
        upper = ttk.Frame(body); body.add(upper,weight=3)
        self.sidepane=ScrollPane(upper,width=215,background=SIDEBAR); self.sidepane.pack(side='left',fill='y')
        self.mainpane=ScrollPane(upper,background=BG); self.mainpane.pack(side='left',fill='both',expand=True)
        sidebar=self.sidepane.content
        self.main=self.mainpane.content
        self.nav_buttons={}
        nav_groups=[('WORKSPACE',['Dashboard','Connection','Device Info']),
                    ('CAPTURE',['Logs','Files','Display']),
                    ('SYSTEM',['Apps','Network','Bluetooth','Automotive','Diagnostics']),
                    ('UTILITIES',['Shell','Favorites','History','Settings'])]
        for group,pages in nav_groups:
            tk.Label(sidebar,text=group,bg=SIDEBAR,fg='#6F90A3',font=(UI_FONT,8,'bold'),anchor='w').pack(fill='x',padx=9,pady=(16,5))
            for p in pages:
                b=tk.Label(sidebar,text=p,anchor='w',bg=SIDEBAR,fg=MUTED,
                           padx=13,pady=9,font=(UI_FONT,10),cursor='hand2')
                b.pack(fill='x',pady=1); self.nav_buttons[p]=b
                b.bind('<Button-1>',lambda e,x=p:self.show_page(x))
                b.bind('<Enter>',lambda e,w=b,x=p:w.configure(bg=CARD if self.page!=x else '#244456'))
                b.bind('<Leave>',lambda e,w=b,x=p:w.configure(bg=CARD if self.page==x else SIDEBAR))
        lower=tk.Frame(body,bg=PANEL,padx=14,pady=10); body.add(lower,weight=2)
        bar=tk.Frame(lower,bg=PANEL); bar.pack(fill='x')
        tk.Label(bar,text='SESSION CONSOLE',bg=PANEL,fg=TEXT,font=(UI_FONT,10,'bold')).pack(side='left')
        self.running = tk.StringVar(value='IDLE')
        self._pill(bar,self.running,GREEN).pack(side='left',padx=12)
        for title,cmd in [('Stop',self.stop),('Clear',self.clear_console),('Copy',self.copy_console),('Save',self.save_console),('Open output',lambda:self.open_folder(OUT))]:
            ttk.Button(bar,text=title,command=cmd,style='Quiet.TButton').pack(side='right',padx=2)
        searchbar=tk.Frame(lower,bg=PANEL); searchbar.pack(fill='x',pady=(8,7))
        tk.Label(searchbar,text='FIND',bg=PANEL,fg=MUTED,font=(UI_FONT,8,'bold')).pack(side='left')
        self.search_var=tk.StringVar(); ttk.Entry(searchbar,textvariable=self.search_var,width=28).pack(side='left',padx=8)
        ttk.Button(searchbar,text='Next',command=self.find_output,style='Quiet.TButton').pack(side='left')
        self.autoscroll=tk.BooleanVar(value=True); ttk.Checkbutton(searchbar,text='Auto-scroll',variable=self.autoscroll).pack(side='left',padx=12)
        self.wrap=tk.BooleanVar(value=False); ttk.Checkbutton(searchbar,text='Wrap',variable=self.wrap,command=self.set_wrap).pack(side='left')
        console_frame=tk.Frame(lower,bg='#080F17'); console_frame.pack(fill='both',expand=True)
        self.console=tk.Text(console_frame,bg='#080F17',fg='#D9E8EF',insertbackground='white',
                             font=(MONO_FONT,10),wrap='none',relief='flat',state='disabled',padx=12,pady=9)
        console_scroll=ttk.Scrollbar(console_frame,orient='vertical',command=self.console.yview,
                                      style='Dark.Vertical.TScrollbar')
        self.console.configure(yscrollcommand=console_scroll.set)
        self.console.pack(side='left',fill='both',expand=True); console_scroll.pack(side='right',fill='y')
        self.console.tag_config('cmd',foreground=ACCENT); self.console.tag_config('err',foreground=RED); self.console.tag_config('meta',foreground=MUTED)
        self.show_page('Dashboard')
        self.after(150,lambda:self.body.sashpos(0,int(self.body.winfo_height()*0.63)))

    def _pill(self,parent,variable,color):
        return tk.Label(parent,textvariable=variable,bg=CARD,fg=color,font=(UI_FONT,8,'bold'),padx=10,pady=6)

    def _shortcuts(self):
        self.bind('<F5>',lambda e:self.refresh_devices())
        self.bind('<Control-l>',lambda e:self.clear_console())
        self.bind('<Control-k>',lambda e:self.show_page('Shell'))
        self.bind('<Control-s>',lambda e:self.save_console())
        self.bind('<Control-c>',lambda e:self._copy_selection())
        if sys.platform=='darwin':
            self.bind('<Command-l>',lambda e:self.clear_console())
            self.bind('<Command-k>',lambda e:self.show_page('Shell'))
            self.bind('<Command-s>',lambda e:self.save_console())

    def _drain(self):
        try:
            while True:
                callback,args=self.jobs.get_nowait(); callback(*args)
        except queue.Empty: pass
        self.after(80,self._drain)

    def ui(self,callback,*args): self.jobs.put((callback,args))
    def worker(self,fn): threading.Thread(target=fn,daemon=True).start()
    def _startup(self):
        if self.preview_mode:
            self.status.set('PREVIEW')
            self.connection_state.set('SAMPLE DEVICE')
            self.selector['values']=['10.19.229.1:5555  [sample]']
            self.device_var.set('10.19.229.1:5555  [sample]')
            self.detail.set('Device: 10.19.229.1:5555  ·  TCP/IP  ·  Android: 14  ·  Build: user  ·  Root: NO  ·  SELinux: Enforcing  [SAMPLE]')
            self._append('[17:22:41] > adb devices -l\n10.19.229.1:5555  device product:example model:IVI_Validation_Unit\nExit Code: 0  ·  Duration: 0.12s\n\n','meta')
            return
        if not self.tools.detect():
            self.status.set('ADB MISSING')
            messagebox.showwarning('Platform Tools','adb.exe was not found. Select the Platform Tools folder.')
            self.choose_tools()
        if self.tools.adb:
            self.status.set('ADB READY')
            self.execute(['version'],device=False,timeout=10)
            self.refresh_devices()

    def choose_tools(self):
        folder=filedialog.askdirectory(title='Select Platform Tools Folder')
        if not folder: return
        self.tools.configured=folder
        if not self.tools.detect() or self.tools.directory.resolve()!=Path(folder).resolve():
            # A local adb has higher priority; a selected directory must contain adb.exe.
            if not (Path(folder)/'adb.exe').is_file():
                messagebox.showerror('Platform Tools','Selected folder does not contain adb.exe.'); return
            self.tools.adb=(Path(folder)/'adb.exe').resolve()
        self.config_data.data['platform_tools']=folder; self.config_data.save()
        self.status.set('ADB READY')
        self.refresh_devices()
        if self.page=='Settings': self.show_page('Settings')

    def _periodic_refresh(self):
        if self.tools.adb and self.stream is None: self.refresh_devices(silent=True)
        self.after(max(5,int(self.config_data.data.get('refresh_seconds',12)))*1000,self._periodic_refresh)

    def refresh_devices(self,silent=False):
        if self.preview_mode: return
        if not self.tools.adb: return
        def job():
            try:
                r=self.tools.run(['devices','-l'],timeout=10)
                self.ui(self._set_devices,r.stdout,r.stderr,not silent)
            except Exception as e: self.ui(self._append,f'Device refresh failed: {e}\n','err')
        self.worker(job)

    def _set_devices(self,out,err,log):
        previous=self.device_var.get(); self.devices=parse_devices(out)
        labels=[f'{d.serial}  [{d.state}]' for d in self.devices]
        self.selector['values']=labels
        chosen=next((x for x in labels if x.startswith(previous.split('  [')[0]+'  [')),labels[0] if labels else 'No devices detected')
        self.device_var.set(chosen)
        if log: self._append(f'[{clock()}] > adb devices -l\n{out}{err}\n','meta')
        self._device_selected()

    def serial(self,required=True):
        if self.preview_mode:
            if required: messagebox.showinfo('Preview mode','This preview does not execute ADB commands.')
            return None
        value=self.device_var.get().split('  [')[0]
        device=next((d for d in self.devices if d.serial==value),None)
        if required and (not device or device.state!='device'):
            messagebox.showwarning('Device unavailable','Select an authorized, online device. Refresh devices if needed.')
            return None
        return value if device else None

    def _device_selected(self):
        serial=self.serial(False)
        d=next((d for d in self.devices if d.serial==serial),None)
        if not d:
            self.connection_state.set('NO DEVICE')
            self.detail.set('Device: none  ·  Android: —  ·  Build: —  ·  Root: —  ·  SELinux: —')
            if self.page=='Files' and getattr(self,'browser_source_key',None) is not None:
                self.browser_source_key=None
                self.browse_remote(self.browser_location)
            return
        self.connection_state.set('CONNECTED' if d.state=='device' else d.state.upper())
        ctype='TCP/IP' if ':' in serial else 'USB'
        self.detail.set(f'Device: {serial}  ·  {ctype}  ·  {d.state}  ·  Android: …  ·  Build: …  ·  Root: …  ·  SELinux: …')
        if self.page=='Files' and getattr(self,'browser_source_key',None)!=(serial,d.state):
            self.browser_source_key=(serial,d.state)
            self.browse_remote(self.browser_location)
        if d.state!='device': return
        def job():
            vals=[]
            for args in (['shell','getprop','ro.build.version.release'],['shell','getprop','ro.build.type'],['shell','id'],['shell','getenforce']):
                try: vals.append(self.tools.run(args,serial,timeout=6).stdout.strip())
                except Exception: vals.append('—')
            self.ui(self._set_detail,serial,ctype,vals)
        self.worker(job)

    def _set_detail(self,serial,ctype,vals):
        if serial!=self.serial(False): return
        root='YES' if 'uid=0(' in vals[2] else 'NO'
        self.detail.set(f'Device: {serial}  ·  {ctype}  ·  Android: {vals[0] or "—"}  ·  Build: {vals[1] or "—"}  ·  Root: {root}  ·  SELinux: {vals[3] or "—"}')

    def _append(self,text,tag=''):
        self.console.configure(state='normal'); self.console.insert('end',text,tag)
        self.console.configure(state='disabled')
        if self.autoscroll.get(): self.console.see('end')

    def _finish(self,result,filtered=None,label=''):
        self.busy=max(0,self.busy-1); self.running.set('RUNNING' if self.busy or self.stream else 'IDLE')
        text=filtered if filtered is not None else result.stdout
        if text: self._append(text + ('' if text.endswith('\n') else '\n'))
        if result.stderr: self._append(result.stderr + ('' if result.stderr.endswith('\n') else '\n'),'err')
        note=f'Exit Code: {result.returncode}  ·  Duration: {result.duration:.2f}s'
        if result.timed_out: note+='  ·  TIMEOUT'
        friendly=friendly_error(result)
        self._append(note+'\n'+(friendly+'\n' if friendly else '')+'\n','err' if result.returncode else 'meta')
        self.config_data.add_history({'timestamp':dt.datetime.now().isoformat(timespec='seconds'),'device':self.last_device or '',
                                      'command':result.argv[1:],'exit_code':result.returncode})
        if label=='connect':
            output=(result.stdout+result.stderr).lower()
            if 'connected to' in output or 'already connected' in output: self.connection_state.set('CONNECTED')
            elif 'unauthorized' in output or 'authenticate' in output: self.connection_state.set('UNAUTHORIZED')
            elif 'offline' in output: self.connection_state.set('OFFLINE')
            else: self.connection_state.set('FAILED')
        if label in ('connect','disconnect','devices'): self.refresh_devices(silent=True)
        if label=='browser-push' and self.page=='Files': self.browse_remote(self.browser_location)

    def execute(self,args,device=True,danger='SAFE',timeout=30,filter_text='',label=''):
        if self.preview_mode:
            messagebox.showinfo('Preview mode','This preview does not execute ADB commands.'); return
        if not self.tools.adb: messagebox.showerror('ADB missing','Select a Platform Tools folder first.'); return
        serial=self.serial() if device else None
        if device and not serial: return
        try: argv=self.tools.argv(list(args),serial)
        except Exception as e: messagebox.showerror('Command error',str(e)); return
        display=subprocess.list2cmdline(argv)
        self.preview.set(display)
        if danger=='BLOCKED': messagebox.showerror('Blocked command','This operation is outside the safe validation scope.'); return
        if danger!='SAFE':
            message='This will reboot the IVI/device. Continue?' if args and args[0]=='reboot' else f'{danger}: Execute this command on {serial or "ADB server"}?\n\n{display}'
            if not messagebox.askyesno('Confirm ADB command',message): return
        self.last_args=list(args); self.last_device=serial
        self._append(f'[{clock()}] > {display}\n','cmd')
        self.busy+=1; self.running.set('RUNNING')
        cancel=threading.Event(); self.active_stops.append(cancel)
        def job():
            try:
                result=self.tools.run(list(args),serial,timeout,stop=cancel)
                filtered=filter_lines(result.stdout,filter_text) if filter_text else None
                self.ui(self._finish,result,filtered,label)
            except Exception as e:
                self.ui(self._append,f'Execution failed: {e}\n','err')
                self.ui(self._decrement)
            finally:
                self.ui(lambda:self.active_stops.remove(cancel) if cancel in self.active_stops else None)
        self.worker(job)

    def _decrement(self): self.busy=max(0,self.busy-1); self.running.set('RUNNING' if self.busy or self.stream else 'IDLE')
    def run_preset(self,name):
        c=COMMANDS[name]; self.execute(c.args,c.device,c.danger,60,c.filter_text,name)

    def stop(self):
        for event in self.active_stops: event.set()
        if self.stream:
            process=self.stream; self.stream=None
            try: process.terminate()
            except OSError: pass
            self.running.set('RUNNING' if self.busy else 'IDLE')
            self._append(f'[{clock()}] Stream stopped by user.\n','meta')

    def start_stream(self,args,filter_text='',kind='stream'):
        if self.preview_mode:
            messagebox.showinfo('Preview mode','This preview does not execute ADB commands.'); return
        if self.stream: messagebox.showinfo('Stream running','Stop the current stream first.'); return
        serial=self.serial()
        if not serial: return
        argv=self.tools.argv(args,serial); self.preview.set(subprocess.list2cmdline(argv))
        self._append(f'[{clock()}] > {subprocess.list2cmdline(argv)}\n','cmd')
        self.running.set('RUNNING · '+kind.upper())
        try: process=self.tools.start(args,serial)
        except Exception as e: self._append(str(e)+'\n','err'); self.running.set('IDLE'); return
        self.stream=process
        def job():
            start=time.monotonic()
            logfile=OUT/'Logcat'/f'logcat_{safe_serial(serial)}_{stamp()}.txt' if kind=='logcat' else None
            try:
                # stdout is line-oriented; stderr is drained after process exits.
                with logfile.open('w',encoding='utf-8') if logfile else open(os.devnull,'w') as saved:
                    for raw in iter(process.stdout.readline,b''):
                        line=raw.decode('utf-8','replace')
                        if logfile: saved.write(line)
                        if not filter_text or filter_lines(line,filter_text): self.ui(self._append,line,'')
                        if process.poll() is not None: break
                err=process.stderr.read().decode('utf-8','replace')
                process.wait()
                if err: self.ui(self._append,err,'err')
                if logfile: self.ui(self._append,f'Logcat saved: {logfile}\n','meta')
                self.ui(self._stream_done,process,time.monotonic()-start)
            except Exception as e: self.ui(self._append,f'Stream failed: {e}\n','err'); self.ui(self._stream_done,process,0)
        self.worker(job)

    def _stream_done(self,process,duration):
        if self.stream is process: self.stream=None
        self.running.set('RUNNING' if self.busy else 'IDLE')
        self._append(f'Exit Code: {process.returncode}  ·  Duration: {duration:.2f}s\n','meta')

    def _clear_main(self):
        for w in self.main.winfo_children(): w.destroy()
    def title_in(self,title,subtitle=''):
        tk.Label(self.main,text=title,bg=BG,fg=TEXT,font=(UI_FONT,22,'bold'),anchor='w').pack(fill='x',pady=(0,3))
        if subtitle: tk.Label(self.main,text=subtitle,bg=BG,fg=MUTED,font=(UI_FONT,10),anchor='w',justify='left',wraplength=980).pack(fill='x',pady=(0,16))
    def section(self,title,subtitle=''):
        head=tk.Frame(self.main,bg=BG); head.pack(fill='x',pady=(16,8))
        tk.Label(head,text=title,bg=BG,fg=TEXT,font=(UI_FONT,12,'bold')).pack(anchor='w')
        if subtitle: tk.Label(head,text=subtitle,bg=BG,fg=MUTED,font=(UI_FONT,9)).pack(anchor='w',pady=(3,0))
    def row(self):
        f=tk.Frame(self.main,bg=BG); f.pack(fill='x',pady=5); return f
    def button(self,parent,text,fn,accent=False):
        b=ttk.Button(parent,text=text,command=fn,style='Accent.TButton' if accent else 'TButton'); b.pack(side='left',padx=3,pady=3); return b
    def presets(self,names):
        names=[n for n in names if n in COMMANDS]
        if not names:return
        grid=tk.Frame(self.main,bg=BG); grid.pack(fill='x',pady=(2,5))
        for col in range(3): grid.grid_columnconfigure(col,weight=1,uniform='command')
        for i,name in enumerate(names):
            c=COMMANDS[name]; color={'SAFE':GREEN,'CAUTION':AMBER,'DESTRUCTIVE':RED}[c.danger_level]
            tile=tk.Frame(grid,bg=CARD,highlightbackground=BORDER,highlightthickness=1,padx=13,pady=10,cursor='hand2')
            tile.grid(row=i//3,column=i%3,sticky='nsew',padx=4,pady=4)
            top=tk.Frame(tile,bg=CARD); top.pack(fill='x')
            title=tk.Label(top,text=name,bg=CARD,fg=TEXT,font=(UI_FONT,10,'bold'),anchor='w')
            title.pack(side='left',fill='x',expand=True)
            level=tk.Label(top,text=c.danger_level,bg=CARD,fg=color,font=(UI_FONT,7,'bold'))
            level.pack(side='right')
            raw='adb '+subprocess.list2cmdline(c.args)
            raw_label=tk.Label(tile,text=raw if len(raw)<=42 else raw[:39]+'…',bg=CARD,fg=MUTED,font=(MONO_FONT,8),anchor='w',justify='left')
            raw_label.pack(fill='x',pady=(7,0))
            def run(event=None,n=name): self.run_preset(n)
            def favorite(event=None,n=name): self.favorite(n)
            for widget in (tile,top,title,level,raw_label):
                widget.bind('<Button-1>',run)
                widget.bind('<Button-3>',favorite)
            Tooltip(tile,f'{raw}\nRight-click to toggle favorite')
    def field(self,parent,label,variable,width=30):
        tk.Label(parent,text=label,bg=parent.cget('bg'),fg=MUTED,font=(UI_FONT,9)).pack(side='left',padx=(7,3))
        e=ttk.Entry(parent,textvariable=variable,width=width); e.pack(side='left',padx=3); return e

    def show_page(self,page):
        descriptions={
            'Dashboard':'Start a validation session and capture evidence from one place.',
            'Connection':'Discover USB devices and manage the remembered TCP/IP target.',
            'Device Info':'Inspect build identity, root and security state.',
            'Logs':'Capture live Android and kernel diagnostics with local filtering.',
            'Apps':'Inspect packages, activities and processes; confirm device changes.',
            'Files':'Browse device storage, transfer artifacts and inspect factory paths read-only.',
            'Display':'Capture the screen, record video and send key events.',
            'Network':'Inspect interfaces, routes, connectivity and ADB TCP state.',
            'Bluetooth':'Review Bluetooth service state, properties and logcat.',
            'Automotive':'Inspect vehicle and IVI services without assuming vendor availability.',
            'Diagnostics':'Generate reports, inspect services and collect support evidence.',
            'Shell':'Run a single ADB or Android shell command with full preview.',
            'Favorites':'Quick access to frequently used presets.',
            'History':'Review and repeat commands from recent sessions.',
            'Settings':'Verify the ADB executable and local storage locations.'}
        self.page=page; self._clear_main(); self.mainpane.reset(); self.title_in(page,descriptions.get(page,''))
        for name,button in self.nav_buttons.items():
            active=name==page
            button.configure(bg=CARD if active else SIDEBAR,fg=TEXT if active else MUTED,
                             font=(UI_FONT,10,'bold' if active else 'normal'))
        self.after_idle(lambda p=page:self._reveal_nav(p))
        if page=='Dashboard':
            self.dashboard_page()
        elif page=='Connection': self.connection_page()
        elif page=='Device Info':
            self.section('Identity and security','Collect a structured device profile, then inspect individual security signals.')
            r=self.row(); self.button(r,'Full Device Info',self.full_info,True)
            self.info_box=tk.Text(self.main,height=12,bg=PANEL,fg=TEXT,font=(MONO_FONT,9),relief='flat',padx=10,pady=8)
            self.info_box.pack(fill='x',pady=8)
            self.presets(['Check Root','Check SELinux','Verified Boot','VBMeta State','ADB Root','ADB Unroot'])
        elif page=='Logs': self.logs_page()
        elif page=='Apps': self.apps_page()
        elif page=='Files': self.files_page()
        elif page=='Display': self.display_page()
        elif page=='Network':
            self.section('Interfaces and connectivity')
            self.presets(['IP Addresses','Routes','Neighbors','Dumpsys connectivity','Dumpsys wifi','Ping','ADB TCP Port','Persistent ADB Port'])
        elif page=='Bluetooth':
            self.section('Service diagnostics')
            self.presets(['Bluetooth State','Bluetooth Properties']); r=self.row(); self.button(r,'Bluetooth Logcat',lambda:self.start_stream(['logcat'],'bluetooth',kind='logcat'))
        elif page=='Automotive':
            self.section('Android Automotive','Availability varies by product build; unavailable services return their ADB error.')
            self.presets(['Car Service','Service List','Audio State','Media Sessions']); self.custom_service()
        elif page=='Diagnostics': self.diagnostics_page()
        elif page=='Shell': self.shell_page()
        elif page=='Favorites': self.favorites_page()
        elif page=='History': self.history_page()
        elif page=='Settings': self.settings_page()

    def _reveal_nav(self,page):
        button=self.nav_buttons.get(page)
        if not button or not button.winfo_exists(): return
        canvas=self.sidepane.canvas
        top=canvas.canvasy(0)
        bottom=top+canvas.winfo_height()
        y=button.winfo_y()
        if y<top or y+button.winfo_height()>bottom:
            total=max(1,self.sidepane.content.winfo_height())
            canvas.yview_moveto(max(0,(y-24)/total))

    def dashboard_page(self):
        summary=tk.Frame(self.main,bg=BG); summary.pack(fill='x',pady=(0,12))
        for col in range(3): summary.grid_columnconfigure(col,weight=1,uniform='summary')
        cards=[('ADB ENGINE',self.status,ACCENT),('DEVICE STATE',self.connection_state,AMBER),
               ('DEFAULT TARGET',tk.StringVar(value=f"{self.config_data.data['target_ip']}:{self.config_data.data['target_port']}"),TEXT)]
        for col,(label,var,color) in enumerate(cards):
            card=tk.Frame(summary,bg=PANEL,highlightthickness=1,highlightbackground=BORDER,padx=15,pady=12)
            card.grid(row=0,column=col,sticky='nsew',padx=4)
            tk.Label(card,text=label,bg=PANEL,fg=MUTED,font=(UI_FONT,8,'bold'),anchor='w').pack(fill='x')
            tk.Label(card,textvariable=var,bg=PANEL,fg=color,font=(UI_FONT,13,'bold'),anchor='w').pack(fill='x',pady=(7,0))
        self.section('Start here','Connect a device, inspect its identity, and capture the evidence needed for a test run.')
        actions=tk.Frame(self.main,bg=BG); actions.pack(fill='x')
        for col in range(4): actions.grid_columnconfigure(col,weight=1,uniform='action')
        action_items=[('01  CONNECT','Discover or connect a target',lambda:self.show_page('Connection')),
                      ('02  DEVICE INFO','Read build and security details',self.full_info),
                      ('03  LIVE LOGCAT','Watch device events',lambda:self.start_stream(['logcat'],kind='logcat')),
                      ('04  SNAPSHOT','Save a validation report',self.snapshot)]
        for i,(title,subtitle,fn) in enumerate(action_items):
            card=tk.Frame(actions,bg=CARD,highlightbackground=BORDER,highlightthickness=1,padx=14,pady=12,cursor='hand2')
            card.grid(row=0,column=i,sticky='nsew',padx=4,pady=3)
            a=tk.Label(card,text=title,bg=CARD,fg=ACCENT,font=(UI_FONT,10,'bold'),anchor='w')
            b=tk.Label(card,text=subtitle,bg=CARD,fg=MUTED,font=(UI_FONT,9),anchor='w')
            a.pack(fill='x'); b.pack(fill='x',pady=(8,0))
            for widget in (card,a,b): widget.bind('<Button-1>',lambda e,command=fn:command())
        self.section('Evidence and quick checks')
        self.presets(['Running Processes','Audio State','Bluetooth State','Dumpsys wifi','Car Service','Touchscreen'])
        r=self.row()
        self.button(r,'Bugreport',self.bugreport)
        self.button(r,'Screenshot',self.screenshot)
        self.button(r,'Support bundle',self.bundle)
        self.button(r,'Open command bar',lambda:self.show_page('Shell'))

    def connection_page(self):
        self.section('TCP/IP target','Your last target is stored locally and can be changed at any time.')
        r=tk.Frame(self.main,bg=PANEL,padx=13,pady=12); r.pack(fill='x',pady=(0,8))
        self.ip=tk.StringVar(value=self.config_data.data['target_ip']); self.port=tk.StringVar(value=self.config_data.data['target_port'])
        self.field(r,'IP',self.ip,20); self.field(r,'Port',self.port,8)
        for text,fn in [('Connect',self.connect),('Disconnect',self.disconnect),('Reconnect',self.reconnect_target)]: self.button(r,text,fn)
        self.section('ADB transport','USB and server changes are confirmed before execution.')
        self.presets(['ADB Devices','ADB Kill Server','ADB Start Server','ADB Reconnect','ADB USB','ADB TCP/IP 5555'])

    def target(self):
        ip=(self.ip.get() if hasattr(self,'ip') else self.config_data.data['target_ip']).strip()
        port=(self.port.get() if hasattr(self,'port') else self.config_data.data['target_port']).strip()
        if not re.fullmatch(r'[A-Za-z0-9.:-]+',ip) or not port.isdigit() or not 1<=int(port)<=65535:
            messagebox.showerror('Invalid target','Enter a valid IP/hostname and TCP port.'); return None
        self.config_data.data.update(target_ip=ip,target_port=port); self.config_data.save()
        return f'{ip}:{port}'
    def connect(self):
        target=self.target()
        if target: self.execute(['connect',target],device=False,label='connect')
    def disconnect(self):
        target=self.target()
        if target: self.execute(['disconnect',target],device=False,danger='CAUTION',label='disconnect')
    def reconnect_target(self):
        target=self.target()
        if not target:return
        if not messagebox.askyesno('Reconnect target',f'Disconnect and reconnect {target}?'):return
        self.preview.set('adb disconnect '+target+'  →  adb connect '+target)
        self.busy+=1; self.running.set('RUNNING · RECONNECT')
        def job():
            try:
                for args in (['disconnect',target],['connect',target]):
                    r=self.tools.run(args,timeout=20)
                    self.ui(self._append,f'[{clock()}] > {subprocess.list2cmdline(r.argv)}\n{r.stdout}{r.stderr}Exit Code: {r.returncode}\n','meta')
            except Exception as e:self.ui(self._append,f'Reconnect failed: {e}\n','err')
            self.ui(self._decrement); self.ui(self.refresh_devices,True)
        self.worker(job)

    def full_info(self):
        serial=self.serial()
        if not serial:return
        self.running.set('RUNNING · DEVICE INFO'); self.busy+=1
        def job():
            lines=[]
            for prop in INFO_PROPS:
                try: r=self.tools.run(['shell','getprop',prop],serial,timeout=8); value=r.stdout.strip() or friendly_error(r) or '—'
                except Exception as e: value=str(e)
                lines.append(f'{prop:<40} {value}')
            for label,args in [('uname',['shell','uname','-a']),('id',['shell','id']),('SELinux',['shell','getenforce'])]:
                try: r=self.tools.run(args,serial,timeout=8); value=r.stdout.strip() or friendly_error(r) or '—'
                except Exception as e: value=str(e)
                lines.append(f'{label:<40} {value}')
            self.ui(self._info_done,'\n'.join(lines))
        self.worker(job)
    def _info_done(self,text):
        self._decrement(); self._append(f'[{clock()}] Full Device Info\n{text}\n','meta')
        if self.page=='Device Info': self.info_box.delete('1.0','end'); self.info_box.insert('end',text)

    def logs_page(self):
        self.section('Live logcat','Streams are saved to the local Logcat folder while the console applies your filter.')
        r=self.row()
        self.button(r,'Live Logcat',self.live_logcat,True)
        self.button(r,'Stop Logcat',self.stop)
        self.button(r,'Clear Logcat',lambda:self.run_preset('Clear Logcat'))
        self.button(r,'Save Console',self.save_console)
        self.button(r,'Save Logcat Dump',self.save_logcat)
        r=self.row(); self.log_level=tk.StringVar(value='Verbose')
        ttk.Label(r,text='Level').pack(side='left')
        Dropdown(r,self.log_level,['Error','Warning','Info','Debug','Verbose'],width=11,background=PANEL).pack(side='left',padx=5)
        self.log_filter=tk.StringVar(); self.field(r,'Python filter (regex or text)',self.log_filter,35)
        presets=['ActivityManager','AndroidRuntime','Bluetooth','Wi-Fi','Audio','Media','Car','Navigation','Touch','USB','SELinux','Crash','ANR']
        self.section('Filter presets','Choose a term, then start the live stream.')
        for i in range(0,len(presets),6):
            row=self.row()
            for term in presets[i:i+6]: self.button(row,term,lambda x=term:self.log_filter.set(x))
        self.section('Kernel and input')
        self.presets(['Kernel Log','Touchscreen','Kernel USB','Kernel Wi-Fi','Kernel Bluetooth','Kernel Errors','Input Devices','Input Capabilities'])
        r=self.row(); self.button(r,'Live Touch Events',lambda:self.start_stream(['shell','getevent'],kind='touch'))
        self.button(r,'Find Touchscreen Input Device',self.find_touch)
    def live_logcat(self):
        levels={'Error':'E','Warning':'W','Info':'I','Debug':'D','Verbose':'V'}
        level=levels.get(self.log_level.get(),'V')
        self.start_stream(['logcat',f'*:{level}'],self.log_filter.get(),kind='logcat')
    def save_logcat(self):
        serial=self.serial()
        if not serial:return
        path=OUT/'Logcat'/f'logcat_{safe_serial(serial)}_{stamp()}.txt'
        self.capture_to_file(['logcat','-d'],path,serial,60)
    def find_touch(self):
        serial=self.serial()
        if not serial:return
        def job():
            try:
                r=self.tools.run(['shell','cat','/proc/bus/input/devices'],serial,timeout=15)
                blocks=[b for b in r.stdout.split('\n\n') if re.search('touch|synaptics|novatek',b,re.I)]
                self.ui(self._append,'Touchscreen candidates:\n'+'\n\n'.join(blocks or ['None found'])+'\n','meta')
            except Exception as e:self.ui(self._append,str(e)+'\n','err')
        self.worker(job)

    def apps_page(self):
        self.section('Inspect','Read package, process and activity state.')
        self.presets(['List Packages','System Packages','Third Party Packages','Running Processes','Top Activity','Activity Stack','CPU Snapshot'])
        self.section('Package actions','Actions that change device state require confirmation.')
        r=self.row(); self.package=tk.StringVar(); self.field(r,'Package',self.package,40)
        self.button(r,'Search Packages',lambda:self.execute(['shell','pm','list','packages'],filter_text=self.package.get().strip()))
        actions=[('Package Info',['shell','dumpsys','package'],'SAFE'),('Force Stop',['shell','am','force-stop'],'CAUTION'),
                 ('Clear App Data',['shell','pm','clear'],'DESTRUCTIVE'),('Launch App',['shell','monkey','-p'],'CAUTION'),
                 ('Uninstall',['uninstall'],'DESTRUCTIVE'),('Disable',['shell','pm','disable-user','--user','0'],'DESTRUCTIVE'),('Enable',['shell','pm','enable'],'CAUTION')]
        for i in range(0,len(actions),4):
            row=self.row()
            for name,prefix,danger in actions[i:i+4]:
                self.button(row,name,lambda n=name,p=prefix,d=danger:self.package_action(n,p,d))
        r=self.row(); self.process_filter=tk.StringVar(); self.field(r,'Process/package filter',self.process_filter,35)
        self.button(r,'Filtered Processes',lambda:self.execute(['shell','ps','-A'],filter_text=self.process_filter.get()))
    def package_action(self,name,prefix,danger):
        pkg=self.package.get().strip()
        if not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+',pkg):
            messagebox.showerror('Package required','Enter a valid Android package name.'); return
        args=prefix+[pkg]+(['1'] if name=='Launch App' else [])
        self.execute(args,danger=danger,timeout=60)

    def files_page(self):
        self.section('Device file browser','Browse the selected Android device without changing its files. Double-click a folder to open it.')
        r=self.row()
        self.browser_path=tk.StringVar(value=self.browser_location)
        path_entry=self.field(r,'DEVICE PATH',self.browser_path,58)
        path_entry.bind('<Return>',lambda e:self.browse_remote(self.browser_path.get()))
        self.button(r,'Go',lambda:self.browse_remote(self.browser_path.get()),True)
        self.button(r,'Up',lambda:self.browse_remote(parent_path(self.browser_location)))
        self.button(r,'Refresh',lambda:self.browse_remote(self.browser_location))
        r=self.row()
        for label,path in [('Internal storage','/sdcard'),('Temporary','/data/local/tmp'),('Factory','/factory'),('Vendor factory','/mnt/vendor/factory')]:
            self.button(r,label,lambda p=path:self.browse_remote(p))
        r=self.row(); self.browser_filter=tk.StringVar()
        filter_entry=self.field(r,'FILTER NAMES',self.browser_filter,32)
        filter_entry.bind('<KeyRelease>',lambda e:self._filter_browser())
        self.browser_status=tk.StringVar(value='Choose an online device to browse its files.')
        tk.Label(self.main,textvariable=self.browser_status,bg=BG,fg=MUTED,font=(UI_FONT,9),anchor='w').pack(fill='x',pady=(5,7))
        tree_frame=tk.Frame(self.main,bg=PANEL,highlightbackground=BORDER,highlightthickness=1)
        tree_frame.pack(fill='x',pady=(0,9))
        self.file_tree=ttk.Treeview(tree_frame,columns=('type','size','modified','permissions'),show='tree headings',height=12,selectmode='browse')
        self.file_tree.heading('#0',text='Name'); self.file_tree.column('#0',width=360,minwidth=180,stretch=True)
        for key,label,width in [('type','Type',85),('size','Size',90),('modified','Modified',175),('permissions','Permissions',115)]:
            self.file_tree.heading(key,text=label); self.file_tree.column(key,width=width,stretch=False,anchor='w')
        self.file_tree.tag_configure('folder',foreground=ACCENT)
        self.file_tree.tag_configure('link',foreground=AMBER)
        tree_scroll=ttk.Scrollbar(tree_frame,orient='vertical',command=self.file_tree.yview,style='Dark.Vertical.TScrollbar')
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        self.file_tree.pack(side='left',fill='both',expand=True); tree_scroll.pack(side='right',fill='y')
        self.file_tree.bind('<Double-1>',lambda e:self.browser_open_selected())
        self.file_tree.bind('<Return>',lambda e:self.browser_open_selected())
        self.file_tree.bind('<<TreeviewSelect>>',lambda e:self._browser_selected())
        self.browser_items={}
        r=self.row()
        self.button(r,'Open folder',self.browser_open_selected)
        self.button(r,'Pull selected…',self.browser_pull_selected)
        self.button(r,'Push file here…',self.browser_push_here)
        self.button(r,'Open local pulls',lambda:self.open_folder(OUT/'Pulls'))
        self.section('Direct transfer','For a path you already know, use the remote path field below.')
        r=self.row(); self.remote=tk.StringVar(value='/data/local/tmp/'); self.field(r,'Remote path',self.remote,38)
        self.button(r,'Push File',self.push_file); self.button(r,'Pull File',self.pull_file)
        self.section('Permission diagnostics','These checks remain read-only.')
        self.presets(['Factory Directory','Factory Context','Vendor Factory Directory','Vendor Factory Context','Factory Mounts','SELinux Denials'])
        self.browse_remote(self.browser_location)

    def browse_remote(self,path):
        try: path=normalize_remote_path(path)
        except ValueError as e: messagebox.showerror('Invalid device path',str(e)); return
        self.browser_location=path
        self.browser_request_id+=1
        request=self.browser_request_id
        if self.page!='Files' or not self.file_tree.winfo_exists(): return
        self.browser_path.set(path)
        self.browser_items={}
        self.browser_entries=[]
        self.file_tree.delete(*self.file_tree.get_children())
        if self.preview_mode:
            samples={'/sdcard':[('DCIM','Folder'),('Documents','Folder'),('Download','Folder'),('validation_notes.txt','File')],
                     '/sdcard/Download':[('bugreport_example.zip','File'),('logcat_example.txt','File')]}
            entries=[RemoteEntry(name,child_path(path,name),kind,None,'—','—') for name,kind in samples.get(path,[])]
            self._render_browser(entries,path,'SAMPLE LISTING · No ADB commands run in preview mode.')
            return
        serial=self.serial(False)
        device=next((d for d in self.devices if d.serial==serial),None)
        if not self.tools.adb or not device or device.state!='device':
            self.browser_status.set('Select an online, authorized device to browse its files.')
            return
        args=list_command(path)
        argv=self.tools.argv(args,serial)
        self.preview.set(subprocess.list2cmdline(argv))
        self.browser_status.set(f'Loading {path} from {serial}…')
        self.busy+=1; self.running.set('RUNNING · FILE BROWSER')
        cancel=threading.Event(); self.active_stops.append(cancel)
        def job():
            try:
                result=self.tools.run(args,serial,timeout=25,stop=cancel)
                entries,skipped=parse_long_listing(result.stdout,path) if result.returncode==0 else ([],[])
                self.ui(self._browser_finished,request,serial,path,result,entries,skipped)
            except Exception as e:
                self.ui(self._browser_failed,request,str(e))
            finally:
                self.ui(lambda:self.active_stops.remove(cancel) if cancel in self.active_stops else None)
        self.worker(job)

    def _browser_finished(self,request,serial,path,result,entries,skipped):
        self._decrement()
        if request!=self.browser_request_id or self.page!='Files' or serial!=self.serial(False): return
        if result.returncode!=0 or result.timed_out:
            error=friendly_error(result) or result.stderr.strip() or result.stdout.strip() or 'Listing failed.'
            self.browser_status.set(error)
            self._append(f'[{clock()}] > {subprocess.list2cmdline(result.argv)}\n{error}\n','err')
            return
        message=f'{len(entries)} item(s) in {path}'
        if skipped: message+=f' · {len(skipped)} listing line(s) could not be parsed'
        self._render_browser(entries,path,message)
        self._append(f'[{clock()}] > {subprocess.list2cmdline(result.argv)}\n{message}\n','meta')

    def _browser_failed(self,request,error):
        self._decrement()
        if request==self.browser_request_id and self.page=='Files': self.browser_status.set(error)
        self._append(f'Device file browser: {error}\n','err')

    def _render_browser(self,entries,path,status):
        if self.page!='Files' or not self.file_tree.winfo_exists(): return
        self.browser_location=path; self.browser_path.set(path)
        self.browser_entries=entries; self.browser_status.set(status)
        self._filter_browser()

    def _filter_browser(self):
        if self.page!='Files' or not self.file_tree.winfo_exists(): return
        needle=self.browser_filter.get().casefold()
        self.file_tree.delete(*self.file_tree.get_children())
        self.browser_items={}
        for index,entry in enumerate(getattr(self,'browser_entries',[])):
            if needle and needle not in entry.name.casefold(): continue
            iid=str(index)
            self.file_tree.insert('', 'end',iid=iid,text=('▸  ' if entry.kind=='Folder' else '    ')+entry.name,
                                  values=(entry.kind,display_size(entry.size),entry.modified,entry.permissions),
                                  tags=(entry.kind.lower(),))
            self.browser_items[iid]=entry

    def _selected_remote(self):
        ids=self.file_tree.selection() if self.page=='Files' and self.file_tree.winfo_exists() else ()
        return self.browser_items.get(ids[0]) if ids else None

    def _browser_selected(self):
        entry=self._selected_remote()
        if entry:
            self.browser_status.set(f'{entry.kind}: {entry.path}'+(f'  →  {entry.target}' if entry.target else ''))
            self.remote.set(entry.path)

    def browser_open_selected(self):
        entry=self._selected_remote()
        if not entry: return
        if entry.kind in ('Folder','Link'): self.browse_remote(entry.path)
        else: self.browser_status.set(f'File selected: {entry.path} · Use Pull selected to copy it locally.')

    def browser_pull_selected(self):
        entry=self._selected_remote()
        if not entry: messagebox.showinfo('Select a file','Select a file or folder in the device browser first.'); return
        if not self.serial(): return
        if entry.kind=='Folder' and not messagebox.askyesno('Pull folder',f'Copy the entire folder from the device?\n\n{entry.path}'):
            return
        destination=filedialog.askdirectory(title='Choose local destination',initialdir=str(OUT/'Pulls'))
        if destination: self.execute(['pull',entry.path,destination],timeout=600)

    def browser_push_here(self):
        if not safe_push_target(self.browser_location):
            messagebox.showwarning('Read-only location','Push is limited to /sdcard and /data/local/tmp from the file browser.')
            return
        if not self.serial(): return
        local=filedialog.askopenfilename(title='Choose a file to push to this device folder')
        if local:
            destination=self.browser_location.rstrip('/')+'/'
            self.execute(['push',local,destination],danger='CAUTION',timeout=300,label='browser-push')
    def push_file(self):
        if not safe_push_target(self.remote.get().strip()):
            messagebox.showwarning('Read-only location','Push is limited to /sdcard and /data/local/tmp from the Files page.')
            return
        local=filedialog.askopenfilename(title='Choose file to push')
        if local:self.execute(['push',local,self.remote.get().strip()],danger='CAUTION',timeout=300)
    def pull_file(self):
        remote=self.remote.get().strip(); destination=filedialog.askdirectory(title='Choose pull destination',initialdir=str(OUT/'Pulls'))
        if remote and destination:self.execute(['pull',remote,destination],timeout=300)

    def display_page(self):
        self.section('Display state')
        self.presets(['Display Info','Window Info','Resolution','Density'])
        self.section('Capture')
        r=self.row(); self.button(r,'Screenshot',self.screenshot,True); self.button(r,'Start Recording',self.start_recording)
        self.button(r,'Stop Recording',self.stop); self.button(r,'Pull Recording',self.pull_recording)
        self.section('Input controls','Keyevents change the device UI and require confirmation.')
        self.presets(['Home','Back','Recent Apps','Volume Up','Volume Down','Mute','Power'])
        r=self.row(); self.keyevent=tk.StringVar(); self.field(r,'Custom keyevent',self.keyevent,22)
        self.button(r,'Send',self.send_keyevent)
    def send_keyevent(self):
        key=self.keyevent.get().strip().upper()
        if re.fullmatch(r'(KEYCODE_[A-Z0-9_]+|[0-9]+)',key): self.execute(['shell','input','keyevent',key],danger='CAUTION')
        else: messagebox.showerror('Invalid keyevent','Use KEYCODE_NAME or a numeric Android key code.')
    def screenshot(self):
        serial=self.serial()
        if not serial:return
        path=OUT/'Screenshots'/f'screenshot_{safe_serial(serial)}_{stamp()}.png'
        self.preview.set(subprocess.list2cmdline(self.tools.argv(['exec-out','screencap','-p'],serial)))
        self.running.set('RUNNING · SCREENSHOT'); self.busy+=1
        def job():
            try:
                p=self.tools.start(['exec-out','screencap','-p'],serial,binary=True)
                data,err=p.communicate(timeout=30)
                if p.returncode or not data.startswith(b'\x89PNG'):
                    self.ui(self._append,f'Screenshot failed: {err.decode("utf-8","replace")}\n','err')
                else:
                    path.write_bytes(data); self.ui(self._append,f'Screenshot saved: {path}\n','meta')
            except Exception as e:self.ui(self._append,f'Screenshot failed: {e}\n','err')
            self.ui(self._decrement)
        self.worker(job)
    def start_recording(self): self.start_stream(['shell','screenrecord','/sdcard/validation_recording.mp4'],kind='recording')
    def pull_recording(self):
        path=OUT/'ScreenRecords'/f'recording_{stamp()}.mp4'
        self.execute(['pull','/sdcard/validation_recording.mp4',str(path)],timeout=300)

    def diagnostics_page(self):
        self.section('Evidence collection','Long tasks run in the background. Use Stop to cancel.')
        r=self.row()
        for title,fn in [('Generate Bugreport…',self.bugreport_as),('Timestamped Bugreport',self.bugreport),
                         ('Capture Validation Snapshot',self.snapshot),('Collect Debug Bundle',self.bundle)]: self.button(r,title,fn)
        self.section('System checks')
        self.presets(['Check Root','Check SELinux','Verified Boot','VBMeta State','Kernel Log','Touchscreen','Kernel Errors',
                      'Storage Overview','Mount Table','Uptime','Date','Memory','CPU Info'])
        self.section('Dumpsys services')
        self.presets([n for n in COMMANDS if n.startswith('Dumpsys ')])
        self.section('Reboot controls','These actions interrupt the IVI/device and always require confirmation.')
        self.presets(['Reboot Android','Reboot Recovery','Reboot Bootloader'])
        self.custom_service()
    def custom_service(self):
        row=self.row(); service=tk.StringVar(); self.field(row,'Custom dumpsys service',service,25)
        self.button(row,'Run',lambda:self.execute(['shell','dumpsys',service.get().strip()]) if re.fullmatch(r'[\w.]+',service.get().strip()) else messagebox.showerror('Invalid service','Enter a service name.'))

    def bugreport(self):
        serial=self.serial()
        if not serial:return
        path=OUT/'Bugreports'/f'bugreport_{safe_serial(serial)}_{stamp()}.zip'
        self.capture_to_file(['bugreport',str(path)],path,serial,900,direct=True)
    def bugreport_as(self):
        serial=self.serial()
        if not serial:return
        chosen=filedialog.asksaveasfilename(title='Save Bugreport',initialdir=str(OUT/'Bugreports'),
                                            initialfile=f'bugreport_{safe_serial(serial)}_{stamp()}.zip',
                                            defaultextension='.zip',filetypes=[('ZIP archive','*.zip')])
        if chosen:
            path=Path(chosen)
            self.capture_to_file(['bugreport',str(path)],path,serial,900,direct=True)
    def capture_to_file(self,args,path,serial,timeout,direct=False):
        display=subprocess.list2cmdline(self.tools.argv(args,serial)); self.preview.set(display)
        self._append(f'[{clock()}] > {display}\n','cmd'); self.busy+=1; self.running.set('RUNNING · CAPTURE')
        cancel=threading.Event(); self.active_stops.append(cancel)
        def job():
            try:
                result=self.tools.run(args,serial,timeout,stop=cancel)
                if not direct and result.returncode==0: path.write_text(result.stdout,encoding='utf-8')
                self.ui(self._append,f'{result.stdout}{result.stderr}\nExit Code: {result.returncode} · Duration: {result.duration:.2f}s\nSaved: {path if path.exists() else "No output file produced"}\n','meta' if result.returncode==0 else 'err')
            except Exception as e:self.ui(self._append,f'Capture failed: {e}\n','err')
            self.ui(self._decrement)
            self.ui(lambda:self.active_stops.remove(cancel) if cancel in self.active_stops else None)
        self.worker(job)

    def snapshot(self):
        serial=self.serial()
        if not serial:return
        path=OUT/'Reports'/f'ValidationSnapshot_{stamp()}.txt'
        self._collection(SNAPSHOT,path,serial)
    def _collection(self,items,path,serial):
        self.busy+=1; self.running.set('RUNNING · REPORT')
        cancel=threading.Event(); self.active_stops.append(cancel)
        def job():
            with path.open('w',encoding='utf-8') as f:
                f.write(f'ADB Validation Console\nCaptured: {dt.datetime.now().isoformat()}\nDevice: {serial}\n')
                for label,args,needs_device in items:
                    if cancel.is_set(): f.write('\nCANCELLED BY USER\n'); break
                    try:
                        r=self.tools.run(args,serial if needs_device else None,timeout=90,stop=cancel)
                        content=f'\n=== {label} ===\n$ {subprocess.list2cmdline(r.argv)}\n{r.stdout}{r.stderr}\nExit: {r.returncode} · Duration: {r.duration:.2f}s\n'
                    except Exception as e: content=f'\n=== {label} ===\nERROR: {e}\n'
                    f.write(content); self.ui(self._append,f'{label}: complete\n','meta')
            self.ui(self._append,f'Report saved: {path}\n','meta'); self.ui(self._decrement)
            self.ui(lambda:self.active_stops.remove(cancel) if cancel in self.active_stops else None)
        self.worker(job)
    def bundle(self):
        serial=self.serial()
        if not serial:return
        import zipfile
        folder=OUT/'SupportBundle'/stamp(); folder.mkdir(parents=True,exist_ok=True)
        items=SNAPSHOT+[(name,args,True) for name,args in [
            ('Logcat',['logcat','-d']),('Kernel',['shell','dmesg']),('Packages',['shell','pm','list','packages']),
            ('Processes',['shell','ps','-A']),('System',['shell','getprop'])]]
        self.busy+=1; self.running.set('RUNNING · SUPPORT BUNDLE')
        cancel=threading.Event(); self.active_stops.append(cancel)
        def job():
            manifest=[]
            for i,(label,args,device) in enumerate(items,1):
                if cancel.is_set(): manifest.append({'status':'cancelled'}); break
                filename=f'{i:02d}_{re.sub("[^A-Za-z0-9_-]","_",label)}.txt'
                try:
                    r=self.tools.run(args,serial if device else None,timeout=90,stop=cancel)
                    (folder/filename).write_text(f'$ {subprocess.list2cmdline(r.argv)}\nExit: {r.returncode}\n{r.stdout}\n{r.stderr}',encoding='utf-8')
                    manifest.append({'name':label,'exit_code':r.returncode,'file':filename})
                except Exception as e: manifest.append({'name':label,'error':str(e)})
                self.ui(self._append,f'Bundle: {label}\n','meta')
            bug=folder/'bugreport.zip'
            if not cancel.is_set():
                try:
                    r=self.tools.run(['bugreport',str(bug)],serial,timeout=900,stop=cancel)
                    manifest.append({'name':'Bugreport','exit_code':r.returncode,'file':bug.name if bug.exists() else None,'stderr':r.stderr})
                except Exception as e: manifest.append({'name':'Bugreport','error':str(e)})
            (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            archive=folder.parent/f'SupportBundle_{folder.name}.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for p in folder.iterdir(): z.write(p,p.name)
            self.ui(self._append,f'Support bundle saved: {archive}\n','meta'); self.ui(self._decrement)
            self.ui(lambda:self.active_stops.remove(cancel) if cancel in self.active_stops else None)
        self.worker(job)

    def shell_page(self):
        self.section('Command bar','Enter one ADB or Android shell command. The complete argv appears in the preview bar.')
        r=self.row(); self.mode=tk.StringVar(value='Shell')
        ttk.Radiobutton(r,text='ADB shell command',variable=self.mode,value='Shell').pack(side='left',padx=8)
        ttk.Radiobutton(r,text='ADB command',variable=self.mode,value='ADB').pack(side='left',padx=8)
        r=self.row(); self.manual=tk.StringVar(); entry=self.field(r,'Command',self.manual,75); entry.focus_set()
        self.button(r,'Run',self.run_manual,True); entry.bind('<Return>',lambda e:self.run_manual())
        ttk.Label(self.main,text='Examples: getprop ro.build.type  ·  ls -la /  ·  dumpsys audio  ·  pm list packages',wraplength=900).pack(anchor='w',pady=8)
    def run_manual(self):
        raw=self.manual.get().strip()
        if not raw:return
        try: args=shlex.split(raw,posix=True)
        except ValueError as e: messagebox.showerror('Command syntax',str(e)); return
        if self.mode.get()=='Shell': args=['shell',*args]
        self.execute(args,device=not(args[0] in ('devices','connect','disconnect','start-server','kill-server','version')),danger=classify_manual(args),timeout=120)

    def favorite(self,name):
        items=self.config_data.data.get('favorites',[])
        if name in items: items.remove(name)
        else: items.append(name)
        self.config_data.data['favorites']=items; self.config_data.save()
        if self.page=='Favorites': self.show_page('Favorites')
        else: self._append(f'{name}: {"removed from" if name not in items else "added to"} favorites\n','meta')
    def favorites_page(self):
        self.section('Saved presets','Right-click a command tile to add or remove it.')
        self.presets([n for n in self.config_data.data.get('favorites',[]) if n in COMMANDS])
    def history_page(self):
        tree=ttk.Treeview(self.main,columns=('time','device','command','exit'),show='headings',height=16)
        for key,width in [('time',160),('device',180),('command',700),('exit',65)]: tree.heading(key,text=key.title()); tree.column(key,width=width)
        rows=self.config_data.data.get('history',[])
        for i,r in enumerate(rows): tree.insert('', 'end',iid=str(i),values=(r.get('timestamp',''),r.get('device',''),subprocess.list2cmdline(r.get('command',[])),r.get('exit_code','')))
        tree.pack(fill='both',expand=True)
        r=self.row()
        def selected():
            ids=tree.selection(); return rows[int(ids[0])] if ids else None
        def again():
            item=selected()
            if item: self.execute(item['command'],device=bool(item.get('device')),danger=classify_manual(item['command']),timeout=120)
        def copy():
            item=selected()
            if item: self.clipboard_clear(); self.clipboard_append(subprocess.list2cmdline(item['command']))
        self.button(r,'Run Again',again); self.button(r,'Copy Command',copy)
    def settings_page(self):
        self.section('Platform Tools','The application directory wins over saved settings. ADB uses this directory as cwd.')
        ttk.Label(self.main,text=f'ADB: {self.tools.adb or "Missing"}',wraplength=900).pack(anchor='w',pady=5)
        ttk.Label(self.main,text=f'Platform Tools: {self.tools.directory if self.tools.adb else "Missing"}',wraplength=900).pack(anchor='w',pady=5)
        r=self.row(); self.button(r,'Select Platform Tools Folder',self.choose_tools); self.button(r,'ADB Version',lambda:self.execute(['version'],device=False))
        ttk.Label(self.main,text=f'Config: {self.config_data.path}\nOutput: {OUT}',wraplength=900).pack(anchor='w',pady=10)

    def clear_console(self): self.console.configure(state='normal'); self.console.delete('1.0','end'); self.console.configure(state='disabled')
    def copy_console(self): self.clipboard_clear(); self.clipboard_append(self.console.get('1.0','end-1c'))
    def _copy_preview(self):
        if self.preview.get()!='—':
            self.clipboard_clear(); self.clipboard_append(self.preview.get())
    def _copy_selection(self):
        try: self.clipboard_clear(); self.clipboard_append(self.console.get('sel.first','sel.last'))
        except tk.TclError: pass
    def save_console(self):
        path=filedialog.asksaveasfilename(initialdir=str(OUT/'Logcat'),initialfile=f'console_{stamp()}.txt',defaultextension='.txt',filetypes=[('Text','*.txt')])
        if path: Path(path).write_text(self.console.get('1.0','end-1c'),encoding='utf-8')
    def find_output(self):
        term=self.search_var.get()
        if not term:return
        start=self.console.index('insert +1c'); found=self.console.search(term,start,stopindex='end',nocase=True)
        if not found: found=self.console.search(term,'1.0',stopindex='end',nocase=True)
        if found:
            self.console.tag_remove('sel','1.0','end'); self.console.tag_add('sel',found,f'{found}+{len(term)}c'); self.console.mark_set('insert',found); self.console.see(found)
    def set_wrap(self): self.console.configure(wrap='word' if self.wrap.get() else 'none')
    def open_folder(self,path):
        if os.name=='nt': os.startfile(str(path))
        elif sys.platform=='darwin': subprocess.Popen(['open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else: messagebox.showinfo('Output folder',str(path))
    def close(self):
        self.stop(); self.config_data.data['geometry']=self.geometry(); self.config_data.save(); self.destroy()

if __name__=='__main__': App().mainloop()
