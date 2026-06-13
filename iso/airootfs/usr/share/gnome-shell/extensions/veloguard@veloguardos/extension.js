// VeloGuard GNOME integration:
//   - VPN quick toggle wired to real providers (Proton/Surfshark/NordVPN) via
//     the veloguard-vpn helper: connect-or-get-a-config, zenity import flow,
//     Tor fallback, and live state sync from the actual WireGuard interfaces.
//   - Bulgarian Mode quick toggle.
//   - a Fedora-style "Update VeloGuardOS on restart" checkbox injected into the
//     end-session (restart/shutdown) dialog when a kernel update is staged.
// Every action runs through bash (so PATH resolves) and fires a notification,
// so a press always gives visible feedback even if the underlying op no-ops.
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {QuickToggle, QuickMenuToggle, SystemIndicator}
    from 'resource:///org/gnome/shell/ui/quickSettings.js';
import * as EndSessionDialog from 'resource:///org/gnome/shell/ui/endSessionDialog.js';
import {CheckBox} from 'resource:///org/gnome/shell/ui/checkBox.js';

const PENDING = '/var/lib/veloguard/staged-kernel/pending.json';
// Arming writes /system-update (root); a polkit rule lets the active local user
// run this fixed wrapper without a password (see 49-veloguard-offline-update.rules).
const ARM = ['pkexec', '/usr/local/bin/veloguard-arm-offline-update'];
// VPN helper (polkit rule 49-veloguard-vpn.rules makes pkexec of it silent for
// wheel users). Exit codes: 2 = no config for that provider yet.
const VPN = '/usr/local/bin/veloguard-vpn';
const VPN_UI = '/usr/local/bin/veloguard-vpn-ui';
const PROVIDERS = [
    ['Proton VPN', 'proton'],
    ['Surfshark', 'surfshark'],
    ['NordVPN', 'nord'],
];
// Trust toggle: world-readable mirror the privileged helper maintains.
const TRUSTED_LIST = '/var/lib/veloguard/trusted-ssids';
const WIFI_TRUST = '/usr/local/bin/veloguard-wifi-trust';

function sh(cmd) {
    try {
        GLib.spawn_command_line_async(`/bin/bash -lc ${GLib.shell_quote(cmd)}`);
    } catch (e) {
        logError(e, 'veloguard');
    }
}

function run(cmd, note) {
    sh(`${cmd}; notify-send "VeloGuard" ${GLib.shell_quote(note)}`);
}

const BgToggle = GObject.registerClass(
class BgToggle extends QuickToggle {
    _init() {
        super._init({title: 'Bulgarian Mode', iconName: 'folder-music-symbolic',
                     toggleMode: true});
        // the script reports failures itself (notify on assets-not-found etc.)
        this.connect('clicked', () => {
            sh('veloguard-bulgarian-mode toggle || ' +
               'notify-send "VeloGuard" "Bulgarian Mode failed — run veloguard-bulgarian-mode selftest"');
            GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
                try { this._sync(); } catch (_e) {}
                return GLib.SOURCE_REMOVE;
            });
        });
        // checked follows the script's pidfile, so the toggle shows the truth
        // even when the mode is flipped from a terminal.
        this._pidfile = `${GLib.get_user_runtime_dir()}/veloguard-bgmode/wall.pid`;
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._sync();
            return GLib.SOURCE_CONTINUE;
        });
        this.connect('destroy', () => {
            if (this._timer)
                GLib.source_remove(this._timer);
            this._timer = 0;
        });
        this._sync();
    }

    _sync() {
        try {
            this.checked = GLib.file_test(this._pidfile, GLib.FileTest.EXISTS);
        } catch (_e) {}
    }
});

const VpnToggle = GObject.registerClass(
class VpnToggle extends QuickMenuToggle {
    _init() {
        super._init({title: 'VPN', iconName: 'network-vpn-symbolic',
                     toggleMode: true});
        this.menu.setHeader('network-vpn-symbolic', 'VeloGuard VPN');
        for (const [label, name] of PROVIDERS)
            this.menu.addAction(label, () => this._connect(name, label));
        this.menu.addAction('Import config…', () => sh(`${VPN_UI} import`));
        this.menu.addAction('Tor fallback', () => sh(
            `if pkexec ${VPN} tor; then notify-send "VeloGuard" "Tor fallback enabled"; ` +
            `else notify-send "VeloGuard" "Tor setup failed"; fi`));

        // Main press: ON → connect the default profile; OFF → tear down.
        this.connect('clicked', () => {
            if (this.checked)
                this._connect('veloguard', 'default profile');
            else
                sh(`pkexec ${VPN} disconnect; notify-send "VeloGuard" "VPN off"`);
            this._syncSoon();
        });

        // The toggle reflects reality, not hope: poll the actual WireGuard
        // interfaces (readable without root) and follow them.
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._sync();
            return GLib.SOURCE_CONTINUE;
        });
        this.connect('destroy', () => {
            if (this._timer)
                GLib.source_remove(this._timer);
            this._timer = 0;
        });
        this._sync();
    }

    _connect(name, label) {
        // rc 2 = no config yet → open the provider's config page and point the
        // user at Import; other failures surface their exit code.
        sh(`pkexec ${VPN} connect ${name}; rc=$?; ` +
           `if [ $rc -eq 0 ]; then notify-send "VeloGuard" "VPN up: ${label} (now the default)"; ` +
           `elif [ $rc -eq 2 ]; then url=$(${VPN} url ${name} 2>/dev/null); ` +
           `[ -n "$url" ] && xdg-open "$url" >/dev/null 2>&1 || true; ` +
           `notify-send "VeloGuard" "No ${label} config yet — download a WireGuard config, then VPN ▸ Import config…"; ` +
           `else notify-send "VeloGuard" "VPN failed (code $rc) — try: veloguard-vpn status"; fi`);
        this._syncSoon();
    }

    _syncSoon() {
        GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 3, () => {
            try { this._sync(); } catch (_e) {}
            return GLib.SOURCE_REMOVE;
        });
    }

    _sync() {
        try {
            const proc = Gio.Subprocess.new(
                ['ip', '-br', 'link', 'show', 'type', 'wireguard'],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
            proc.communicate_utf8_async(null, null, (p, res) => {
                try {
                    const [, out] = p.communicate_utf8_finish(res);
                    const ifaces = (out ?? '').trim().split('\n').filter(Boolean)
                        .map(l => l.split(/\s+/)[0].replace(/@.*$/, ''));
                    this.checked = ifaces.length > 0;
                    this.subtitle = ifaces[0] ?? null;
                } catch (_e) {}
            });
        } catch (_e) {}
    }
});

// "Trust this Wi-Fi": checked = network is in the guard's trusted list. Turning
// it OFF marks the current SSID untrusted and the helper brings the VPN up (no
// prompt) if a config is available — exactly the requested behavior.
const TrustToggle = GObject.registerClass(
class TrustToggle extends QuickToggle {
    _init() {
        super._init({title: 'Trust Wi-Fi', iconName: 'network-wireless-symbolic',
                     toggleMode: true});
        this._ssid = null;
        this.connect('clicked', () => {
            if (!this._ssid) { this.checked = false; return; }   // not on Wi-Fi
            const action = this.checked ? 'trust' : 'untrust';
            sh(`r=$(pkexec ${WIFI_TRUST} ${action}); case "$r" in ` +
               `trusted) notify-send "VeloGuard" "Wi-Fi trusted — no auto-VPN";; ` +
               `untrusted) notify-send "VeloGuard" "Wi-Fi untrusted — VPN connecting";; ` +
               `untrusted-no-vpn) notify-send "VeloGuard" "Wi-Fi untrusted — import a VPN config to auto-protect";; ` +
               `esac`);
            this._syncSoon();
        });
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._sync();
            return GLib.SOURCE_CONTINUE;
        });
        this.connect('destroy', () => {
            if (this._timer) GLib.source_remove(this._timer);
            this._timer = 0;
        });
        this._sync();
    }

    _syncSoon() {
        GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 3, () => {
            try { this._sync(); } catch (_e) {}
            return GLib.SOURCE_REMOVE;
        });
    }

    _sync() {
        try {
            const proc = Gio.Subprocess.new(
                ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
            proc.communicate_utf8_async(null, null, (p, res) => {
                try {
                    const [, out] = p.communicate_utf8_finish(res);
                    let ssid = null;
                    for (const l of (out ?? '').split('\n'))
                        if (l.startsWith('yes:')) { ssid = l.slice(4); break; }
                    this._ssid = ssid;
                    if (!ssid) { this.subtitle = 'not on Wi-Fi'; this.checked = false; return; }
                    this.subtitle = ssid;
                    let trusted = false;
                    try {
                        const [ok, bytes] = GLib.file_get_contents(TRUSTED_LIST);
                        if (ok) trusted = new TextDecoder().decode(bytes)
                            .split('\n').includes(ssid);
                    } catch (_e) {}
                    this.checked = trusted;
                } catch (_e) {}
            });
        } catch (_e) {}
    }
});

const Indicator = GObject.registerClass(
class Indicator extends SystemIndicator {
    _init() {
        super._init();
        this._items = [new VpnToggle(), new TrustToggle(), new BgToggle()];
        this._items.forEach(i => this.quickSettingsItems.push(i));
    }
});

// --- Fedora-style offline-update checkbox on the restart dialog -------------
// All of this is wrapped so a GNOME-version mismatch can never block restart:
// worst case the checkbox doesn't show and the dialog behaves normally.

function pendingVersion() {
    try {
        const [ok, bytes] = GLib.file_get_contents(PENDING);
        if (!ok) return null;
        return JSON.parse(new TextDecoder().decode(bytes)).version || null;
    } catch (_e) {
        return null;
    }
}

let _origOpen = null, _origConfirm = null;

function _ensureCheckbox(dlg) {
    const v = pendingVersion();
    const showable = dlg._type === 1 || dlg._type === 2;   // shutdown / restart
    if (!dlg._veloCheck) {
        if (!v || !showable) return;                       // nothing to offer
        dlg._veloCheck = new CheckBox('Update VeloGuardOS on restart');
        const box = dlg._messageDialogContent ?? dlg.contentLayout ?? null;
        if (box && box.add_child) box.add_child(dlg._veloCheck);
    }
    if (dlg._veloCheck) {
        dlg._veloCheck.visible = !!v && showable;
        const label = dlg._veloCheck.getLabelActor && dlg._veloCheck.getLabelActor();
        if (v && label) label.text = `Update VeloGuardOS (kernel ${v}) on restart`;
    }
}

function patchEndSession() {
    const proto = EndSessionDialog.EndSessionDialog && EndSessionDialog.EndSessionDialog.prototype;
    if (!proto) return;
    _origOpen = proto.open;
    proto.open = function (...args) {
        try { _ensureCheckbox(this); } catch (e) { logError(e, 'veloguard'); }
        return _origOpen.apply(this, args);
    };
    if (typeof proto._confirm === 'function') {
        _origConfirm = proto._confirm;
        proto._confirm = function (signal) {
            try {
                if (this._veloCheck && this._veloCheck.visible && this._veloCheck.checked) {
                    // spawn_sync: make sure /system-update is armed BEFORE the
                    // reboot proceeds (polkit lets the active user do it silently).
                    GLib.spawn_sync(null, ARM, null, GLib.SpawnFlags.SEARCH_PATH, null);
                }
            } catch (e) { logError(e, 'veloguard'); }
            return _origConfirm.call(this, signal);
        };
    }
}

function unpatchEndSession() {
    const proto = EndSessionDialog.EndSessionDialog && EndSessionDialog.EndSessionDialog.prototype;
    if (!proto) return;
    if (_origOpen) { proto.open = _origOpen; _origOpen = null; }
    if (_origConfirm) { proto._confirm = _origConfirm; _origConfirm = null; }
}

export default class VeloGuardToggles {
    enable() {
        this._indicator = new Indicator();
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
        try { patchEndSession(); } catch (e) { logError(e, 'veloguard endSession'); }
    }
    disable() {
        try { unpatchEndSession(); } catch (e) { logError(e, 'veloguard'); }
        this._indicator?.quickSettingsItems.forEach(i => i.destroy());
        this._indicator?.destroy();
        this._indicator = null;
    }
}
