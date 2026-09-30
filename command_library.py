"""Catalog of typed, visible ADB presets. No shell=True is used."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Command:
    name: str
    description: str
    args: tuple[str, ...]
    category: str
    danger_level: str = 'SAFE'
    device: bool = True
    filter_text: str = ''

COMMANDS = {}
def add(category, name, command, description='', danger='SAFE', device=True, filter_text=''):
    # Presets contain only static commands. User input is built separately as an argv array.
    import shlex
    args = tuple(shlex.split(command))
    COMMANDS[name] = Command(name, description or name, args, category, danger, device, filter_text)

for name, cmd in {
    'ADB Devices':'devices -l','ADB Kill Server':'kill-server','ADB Start Server':'start-server',
    'ADB Reconnect':'reconnect','ADB USB':'usb','ADB TCP/IP 5555':'tcpip 5555'}.items():
    add('Connection',name,cmd,danger='CAUTION' if name not in ('ADB Devices',) else 'SAFE',device=False)
for category, entries in {
 'System':{'Uptime':'shell uptime','Date':'shell date','Memory':'shell free -m','CPU Info':'shell cat /proc/cpuinfo','Memory Info':'shell cat /proc/meminfo'},
 'Build':{'All Properties':'shell getprop','Build Type':'shell getprop ro.build.type'},
 'Apps':{'List Packages':'shell pm list packages','System Packages':'shell pm list packages -s','Third Party Packages':'shell pm list packages -3','Running Processes':'shell ps -A','CPU Snapshot':'shell top -n 1','Top Activity':'shell dumpsys activity top','Activity Stack':'shell dumpsys activity activities'},
 'Network':{'IP Addresses':'shell ip addr','Routes':'shell ip route','Neighbors':'shell ip neigh','Ping':'shell ping -c 4 8.8.8.8','ADB TCP Port':'shell getprop service.adb.tcp.port','Persistent ADB Port':'shell getprop persist.adb.tcp.port'},
 'Bluetooth':{'Bluetooth State':'shell dumpsys bluetooth_manager','Bluetooth Properties':'shell getprop'},
 'Audio':{'Audio State':'shell dumpsys audio','Audio Flinger':'shell dumpsys media.audio_flinger','Media Sessions':'shell dumpsys media_session'},
 'Automotive':{'Car Service':'shell dumpsys car_service','Service List':'shell service list'},
 'Display':{'Display Info':'shell dumpsys display','Window Info':'shell dumpsys window','Resolution':'shell wm size','Density':'shell wm density'},
 'Files':{'List /sdcard':'shell ls -lah /sdcard','List /data/local/tmp':'shell ls -lah /data/local/tmp'},
 'Security':{'Check Root':'shell id','Check SELinux':'shell getenforce','Verified Boot':'shell getprop ro.boot.verifiedbootstate','VBMeta State':'shell getprop ro.boot.vbmeta.device_state','Factory Directory':'shell ls -ld /factory','Factory Context':'shell ls -ldZ /factory','Vendor Factory Directory':'shell ls -ld /mnt/vendor/factory','Vendor Factory Context':'shell ls -ldZ /mnt/vendor/factory','Mounts':'shell mount','Factory Mounts':'shell mount','SELinux Denials':'logcat -b all -d'},
 'Kernel':{'Kernel Log':'shell dmesg','Touchscreen':'shell dmesg','Kernel USB':'shell dmesg','Kernel Wi-Fi':'shell dmesg','Kernel Bluetooth':'shell dmesg','Kernel Errors':'shell dmesg','Input Devices':'shell cat /proc/bus/input/devices','Input Capabilities':'shell getevent -lp'},
 'Storage':{'Storage Overview':'shell df -h','Disk Usage':'shell df -h','Mount Table':'shell cat /proc/mounts'},
 'Diagnostics':{'Logcat Dump':'logcat -d','Crash Buffer':'logcat -b crash -d'},
}.items():
    for name, cmd in entries.items():
        filt = {'Touchscreen':'synaptics|novatek|touch','Kernel USB':'usb','Kernel Wi-Fi':'wifi|wlan',
                'Kernel Bluetooth':'bluetooth|bt','Kernel Errors':'error|fail|denied',
                'SELinux Denials':'avc: denied','Bluetooth Properties':'bluetooth',
                'Factory Mounts':'factory',
                'Service List':'car|vehicle|audio|navigation|media'}.get(name,'')
        add(category,name,cmd,filter_text=filt)
for service in ('activity','window','package','power','battery','display','input','audio','media.audio_flinger','media_session','bluetooth_manager','wifi','connectivity','usb','meminfo','cpuinfo'):
    add('Dumpsys',f'Dumpsys {service}',f'shell dumpsys {service}')
for name,key in {'Home':'KEYCODE_HOME','Back':'KEYCODE_BACK','Recent Apps':'KEYCODE_APP_SWITCH','Volume Up':'KEYCODE_VOLUME_UP','Volume Down':'KEYCODE_VOLUME_DOWN','Mute':'KEYCODE_VOLUME_MUTE','Power':'KEYCODE_POWER'}.items():
    add('Input',name,f'shell input keyevent {key}',danger='CAUTION')
for name, cmd in {'Reboot Android':'reboot','Reboot Recovery':'reboot recovery','Reboot Bootloader':'reboot bootloader',
                  'ADB Root':'root','ADB Unroot':'unroot','Clear Logcat':'logcat -c'}.items():
    add('Diagnostics',name,cmd,danger='DESTRUCTIVE' if name.startswith('Reboot') else 'CAUTION')

INFO_PROPS = ['ro.product.manufacturer','ro.product.model','ro.product.device','ro.product.name',
              'ro.build.version.release','ro.build.version.sdk','ro.build.version.security_patch',
              'ro.build.id','ro.build.display.id','ro.build.type','ro.build.tags','ro.debuggable',
              'ro.secure','ro.adb.secure','ro.boot.verifiedbootstate','ro.boot.vbmeta.device_state']
SNAPSHOT = [('Devices',['devices','-l'],False)] + [(p,['shell','getprop',p],True) for p in INFO_PROPS] + [
    (n,a,True) for n,a in [('Identity',['shell','id']),('SELinux',['shell','getenforce']),('Uptime',['shell','uptime']),
    ('Storage',['shell','df','-h']),('IP',['shell','ip','addr']),('Routes',['shell','ip','route']),
    ('Activity',['shell','dumpsys','activity','top']),('Audio',['shell','dumpsys','audio']),
    ('Bluetooth',['shell','dumpsys','bluetooth_manager']),('Wi-Fi',['shell','dumpsys','wifi']),
    ('Connectivity',['shell','dumpsys','connectivity']),('Display',['shell','dumpsys','display'])]]
